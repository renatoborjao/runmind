import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.onboarding.onboarding_flow import OnboardingFlow
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MODULE = "app.application.onboarding.onboarding_flow"

PHONE = "5511900000000"

# Sábado 25/07/2026: fim da semana. Com os dias de treino dos cenários,
# sobra <2 dia -> onboarding vai direto pra próxima semana (sem perguntar),
# concluindo com "Cadastro feito" (mantém o comportamento dos testes base).
FIM_DE_SEMANA = date(2026, 7, 25)

# Segunda 20/07/2026: começo da semana, sobram 2+ dias -> pergunta.
COMECO_DA_SEMANA = date(2026, 7, 20)


def _repos(tmp_path):

    onboarding_repo = OnboardingStateRepository()
    onboarding_repo.storage = tmp_path / "onboarding"
    onboarding_repo.storage.mkdir()

    profile_repo = RunnerProfileRepository()
    profile_repo.storage = tmp_path / "profiles"
    profile_repo.storage.mkdir()

    return onboarding_repo, profile_repo


def _run_conversation(tmp_path, exchanges, today=FIM_DE_SEMANA):
    """exchanges: lista de (texto_do_corredor, resposta_do_parser).
    Retorna as respostas do bot. `today` controla a régua da semana."""

    onboarding_repo, profile_repo = _repos(tmp_path)

    replies = []

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.today_local", return_value=today),
        patch(
            f"{MODULE}.OnboardingFlow._build_plan_message",
            new=AsyncMock(return_value="[PLANO DA SEMANA]"),
        ),
    ):

        # por padrão, Strava ainda não conectado ao concluir
        mock_token_store.return_value.load.return_value = None

        # a primeira mensagem (boas-vindas) não passa pelo parser
        parsed_answers = [parsed for _, parsed in exchanges[1:]]

        mock_parser.parse = AsyncMock(side_effect=parsed_answers)

        for text, _ in exchanges:

            replies.append(
                asyncio.run(
                    OnboardingFlow.handle("whatsapp", PHONE, text),
                )
            )

    return replies, onboarding_repo, profile_repo


FULL_CONVERSATION = [
    # primeira mensagem não é parseada (parser nem é chamado),
    # mas mantemos o par para alinhar o side_effect
    ("oi", {}),
    ("me chamo Fulano", {"name": "Fulano"}),
    ("33", {"age": 33}),
    ("91kg", {"weight": 91.0}),
    ("1,78", {"height": 1.78}),
    ("não uso", {"has_strava": False}),
    ("criei", {"created": True}),
    ("sim, corro", {"runs_today": True}),
    ("2x por semana", {"runs_per_week": 2}),
    ("uns 5km", {"typical_km": 5.0}),
    ("não, treino por conta", {"has_coach": False}),
    ("uns 32 minutos", {"typical_minutes": 32.0}),
    ("terça e sábado", {"days": ["Tuesday", "Saturday"]}),
    ("isso mesmo", {"confirmed": True}),
    (
        "quero correr 10km em 55 minutos",
        {
            "goal": "10 km em 55 minutos",
            "target_race": "10 km",
            "target_time": "00:55:00",
        },
    ),
    ("sim, pode montar", {"confirmed": True}),
]

# índice da resposta que trata o Strava (após nome, idade, peso, altura)
STRAVA_REPLY_INDEX = 5


def test_full_onboarding_without_strava_creates_profile(tmp_path):

    replies, onboarding_repo, profile_repo = _run_conversation(
        tmp_path,
        FULL_CONVERSATION,
    )

    # primeira resposta dá boas-vindas e pede o nome
    assert "como você se chama" in replies[0]

    # sem conta no Strava: instrução de CRIAR, e o fluxo ESPERA (gate) —
    # ainda sem link de conexão
    assert "cria" in replies[STRAVA_REPLY_INDEX].lower()
    assert "connect" not in replies[STRAVA_REPLY_INDEX]

    # depois de confirmar que criou: manda o link e segue pro "já corre hoje"
    assert (
        f"/api/v1/strava/connect?state=wa:{PHONE}"
        in replies[STRAVA_REPLY_INDEX + 1]
    )
    assert "já corre hoje" in replies[STRAVA_REPLY_INDEX + 1]

    # a última conclui com o plano
    assert "Cadastro feito, Fulano" in replies[-1]
    assert "[PLANO DA SEMANA]" in replies[-1]

    # Strava ainda não conectado: lembrete no final
    assert "conectar seu Strava" in replies[-1]

    # perfil criado com os dados do questionário
    profile_file = profile_repo.storage / "fulano.json"
    data = json.loads(profile_file.read_text(encoding="utf-8"))

    assert data["name"] == "Fulano"
    assert data["phone"] == PHONE
    assert data["weekly_training_days"] == 2
    assert data["preferred_running_days"] == ["Tuesday", "Saturday"]
    assert data["initial_pace_min_km"] == 6.4  # 32 min / 5 km
    assert data["initial_weekly_km"] == 10.0  # 2x de 5 km
    assert data["goal"] == "10 km em 55 minutos"

    # estado de onboarding apagado ao concluir
    assert onboarding_repo.load(PHONE) is None


# para no "ainda não": o gate segura o cadastro até o atleta criar a conta.
# (o avanço com "criei" é coberto por test_full_onboarding_without_strava_...)
STRAVA_STALL_CONVERSATION = [
    ("oi", {}),
    ("Bia", {"name": "Bia"}),
    ("29", {"age": 29}),
    ("60kg", {"weight": 60.0}),
    ("1,65", {"height": 1.65}),
    ("não tenho", {"has_strava": False}),
    ("ainda não", {"created": False}),
]


def test_no_strava_gates_onboarding_until_account_created(tmp_path):
    """Sem conta no Strava, o cadastro PARA no passo de criação e não avança
    (nem manda o link) enquanto o atleta não confirma que criou."""

    replies, onboarding_repo, _ = _run_conversation(
        tmp_path,
        STRAVA_STALL_CONVERSATION,
    )

    # resposta ao "não tenho": guia a criação, ainda SEM link de conexão
    assert "cria" in replies[5].lower()
    assert "connect" not in replies[5]

    # "ainda não": continua PARADO no passo de espera, sem avançar nem link
    assert "connect" not in replies[6]
    assert onboarding_repo.load(PHONE)["step"] == "AWAIT_STRAVA_SIGNUP"


# km típico em FAIXA ("de 5 a 15 km"): o pace não pode sair da média (10) —
# o passo pede um treino concreto e calcula o pace da distância cravada.
RANGE_PACE_CONVERSATION = [
    ("oi", {}),
    ("Ana", {"name": "Ana"}),
    ("30", {"age": 30}),
    ("62kg", {"weight": 62.0}),
    ("1,68", {"height": 1.68}),
    ("tenho sim", {"has_strava": True}),
    ("sim, corro", {"runs_today": True}),
    ("3x", {"runs_per_week": 3}),
    (
        "de 5 a 15 km",
        {"typical_km": 10.0, "typical_km_min": 5.0, "typical_km_max": 15.0},
    ),
    ("não, por conta", {"has_coach": False}),
    ("8 km em 50 min", {"pace_distance_km": 8.0, "typical_minutes": 50.0}),
    ("terça e sábado", {"days": ["Tuesday", "Saturday"]}),
    ("isso", {"confirmed": True}),
    ("saúde", {"goal": "Saúde", "target_race": None, "target_time": None}),
    ("sim", {"confirmed": True}),
]


def test_range_km_asks_concrete_run_and_uses_stated_distance(tmp_path):
    """Faixa de km: o passo do pace pede km + tempo e o pace sai da distância
    que o atleta cravou (50 min / 8 km = 6.25), não da média (50/10 = 5.0)."""

    replies, _, profile_repo = _run_conversation(
        tmp_path,
        RANGE_PACE_CONVERSATION,
    )

    # após o treinador, a pergunta do pace pede um treino concreto
    assert "quantos km e em quanto tempo" in replies[9]

    # pace calculado da distância cravada (8 km), não da média (10 km)
    data = json.loads(
        (profile_repo.storage / "ana.json").read_text(encoding="utf-8")
    )
    assert data["initial_pace_min_km"] == 6.25


def test_multiple_objectives_preserved_in_goal(tmp_path):
    """O atleta cita VÁRIOS objetivos (saúde + emagrecer + marca): o perfil
    guarda a descrição inteira (não trunca) e ainda extrai o alvo concreto."""

    conversation = FULL_CONVERSATION[:13] + [
        ("agora sim", {"confirmed": True}),  # CONFIRM_DAYS -> ASK_GOAL
        (
            "quero saúde, emagrecer e correr 10km em 55min",
            {
                "goal": "saúde, emagrecer e correr 10 km em 55 min",
                "target_race": "10 km",
                "target_time": "00:55:00",
                "race_date": None,
            },
        ),
        ("sim, pode montar", {"confirmed": True}),
    ]

    replies, _, profile_repo = _run_conversation(tmp_path, conversation)

    data = json.loads(
        (profile_repo.storage / "fulano.json").read_text(encoding="utf-8")
    )

    # a descrição preserva TODOS os objetivos citados
    assert data["goal"] == "saúde, emagrecer e correr 10 km em 55 min"

    # e o alvo de performance concreto continua sendo extraído
    assert data["target_race"] == "10 km"
    assert data["target_time"] == "00:55:00"


NON_RUNNER_CONVERSATION = [
    ("oi", {}),
    ("Adolfo", {"name": "Adolfo"}),
    ("35", {"age": 35}),
    ("138kg", {"weight": 138.0}),
    ("1,88", {"height": 1.88}),
    ("sim", {"has_strava": True}),
    ("não corro, só caminho", {"runs_today": False}),
    (
        "trote 1 min e caminho 3 min",
        {
            "mobility": "run_walker",
            "continuous_run_minutes": 1,
            "walk_speed_kmh": 5.5,
        },
    ),
    ("de segunda a sexta", {"days": [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    ]}),
    ("sim", {"confirmed": True}),
    ("saúde", {"goal": "Saúde", "target_race": None,
                "target_time": None}),
    ("sim", {"confirmed": True}),
]


def test_non_runner_captures_movement_and_stores_capability(tmp_path):

    replies, _, profile_repo = _run_conversation(
        tmp_path,
        NON_RUNNER_CONVERSATION,
    )

    # após "não corro", pergunta como ele se move hoje (base do run/walk)
    assert "como você se movimenta" in replies[6]

    # os dias são confirmados antes de seguir (eco dos dias escolhidos)
    assert "confirmar" in replies[8].lower()

    # o resumo reflete a capacidade (agora um passo depois, após confirmar)
    assert "trote e caminhada" in replies[10]

    assert "Cadastro feito, Adolfo" in replies[-1]

    data = json.loads(
        (profile_repo.storage / "adolfo.json").read_text(encoding="utf-8")
    )

    assert data["mobility"] == "run_walker"
    assert data["continuous_run_minutes"] == 1.0
    assert data["walk_pace_min_km"] == round(60 / 5.5, 2)


def test_midweek_asks_week_choice_then_finishes(tmp_path):
    """Começo da semana, 2+ dias por vir: pergunta esta/próxima e só
    depois conclui com o plano."""

    conversation = FULL_CONVERSATION + [
        ("pode ser essa mesma", {"start_week": "current"}),
    ]

    replies, onboarding_repo, _ = _run_conversation(
        tmp_path,
        conversation,
        today=COMECO_DA_SEMANA,
    )

    # a resposta ao "confirmar" é a pergunta da semana (não o plano ainda)
    week_question = replies[-2]
    assert "nesta semana" in week_question
    assert "próxima segunda" in week_question
    # lista os dias que ainda dá pra treinar (terça e sábado)
    assert "terça-feira" in week_question
    assert "sábado" in week_question
    assert "[PLANO DA SEMANA]" not in week_question

    # após escolher, conclui com o plano
    assert "Cadastro feito, Fulano" in replies[-1]
    assert "[PLANO DA SEMANA]" in replies[-1]

    # onboarding encerrado
    assert onboarding_repo.load(PHONE) is None


def test_near_end_of_week_skips_question(tmp_path):
    """Fim da semana (<2 dias): monta direto, sem perguntar."""

    replies, onboarding_repo, _ = _run_conversation(
        tmp_path,
        FULL_CONVERSATION,
        today=FIM_DE_SEMANA,
    )

    # concluiu direto no confirmar, sem passo de escolha de semana
    assert "Cadastro feito, Fulano" in replies[-1]
    assert "nesta semana" not in replies[-1]
    assert onboarding_repo.load(PHONE) is None


def test_should_ask_week_true_at_start_of_week():

    assert OnboardingFlow._should_ask_week(
        ["Tuesday", "Saturday"],
        COMECO_DA_SEMANA,
    ) is True


def test_should_ask_week_false_near_end():

    # sábado: só sábado ainda por vir (1 dia < 2)
    assert OnboardingFlow._should_ask_week(
        ["Tuesday", "Saturday"],
        FIM_DE_SEMANA,
    ) is False


def test_remaining_day_labels_midweek_keeps_order():

    # quinta 23/07: dos dias ter/qui/sáb restam quinta e sábado
    labels = OnboardingFlow._remaining_day_labels(
        ["Tuesday", "Thursday", "Saturday"],
        date(2026, 7, 23),
    )

    assert labels == ["quinta-feira", "sábado"]


def test_strava_yes_sends_connect_link_and_still_asks_pace(tmp_path):

    conversation = [
        ("oi", {}),
        ("Ciclano", {"name": "Ciclano"}),
        ("40", {"age": 40}),
        ("80kg", {"weight": 80.0}),
        ("1.70", {"height": 1.70}),
        ("uso sim", {"has_strava": True}),
        ("sim", {"runs_today": True}),
        ("3x", {"runs_per_week": 3}),
        ("6km", {"typical_km": 6.0}),
        ("não tenho treinador", {"has_coach": False}),
        # pace é perguntado mesmo com Strava (a conexão pode demorar)
        ("uns 40 minutos", {"typical_minutes": 40.0}),
        (
            "segunda, quarta e sexta",
            {"days": ["Monday", "Wednesday", "Friday"]},
        ),
        ("confirmo", {"confirmed": True}),
        ("saúde", {"goal": "Saúde", "target_race": None,
                    "target_time": None}),
        ("sim", {"confirmed": True}),
    ]

    replies, _, profile_repo = _run_conversation(tmp_path, conversation)

    # link de conexão com state=telefone (após nome, idade, peso, altura)
    strava_reply = replies[5]
    assert f"/api/v1/strava/connect?state=wa:{PHONE}" in strava_reply

    # sequência: já corre? -> frequência -> km -> treinador -> pace -> dias
    assert "já corre hoje" in strava_reply
    assert "Quantas vezes" in replies[6]
    assert "quantos km" in replies[7]
    assert "treinador" in replies[8]
    assert "em quanto tempo" in replies[9]
    assert "Quais dias" in replies[10]

    data = json.loads(
        (profile_repo.storage / "ciclano.json").read_text(
            encoding="utf-8",
        )
    )
    # pace autodeclarado vale até o histórico real chegar
    assert data["initial_pace_min_km"] == 6.67  # 40 min / 6 km


def test_no_strava_reminder_when_already_connected(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.today_local", return_value=FIM_DE_SEMANA),
        patch(
            f"{MODULE}.OnboardingFlow._build_plan_message",
            new=AsyncMock(return_value="[PLANO]"),
        ),
    ):

        # Strava já conectado durante o onboarding
        mock_token_store.return_value.load.return_value = {
            "access_token": "x",
        }

        mock_parser.parse = AsyncMock(
            side_effect=[p for _, p in FULL_CONVERSATION[1:]],
        )

        replies = [
            asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, text))
            for text, _ in FULL_CONVERSATION
        ]

    assert "Cadastro feito" in replies[-1]
    assert "conectar seu Strava" not in replies[-1]


def test_unparsed_answer_repeats_question(tmp_path):

    conversation = [
        ("oi", {}),
        ("asdfgh", {}),  # parser não entendeu o nome
        ("Fulano", {"name": "Fulano"}),
    ]

    replies, *_ = _run_conversation(tmp_path, conversation)

    assert "não consegui entender" in replies[1]
    assert "como você se chama" in replies[1]
    assert "Prazer, Fulano" in replies[2]


def test_confirm_days_step_echoes_chosen_days(tmp_path):
    """Depois dos dias, o bot ecoa a escolha e pede confirmação antes de
    ir pro objetivo (evita desvio de interpretação)."""

    replies, onboarding_repo, _ = _run_conversation(
        tmp_path,
        FULL_CONVERSATION[:13],  # até a resposta dos dias
    )

    # resposta à escolha dos dias: eco + pedido de confirmação
    days_confirm = replies[-1]
    assert "confirmar" in days_confirm.lower()
    assert "terça-feira" in days_confirm
    assert "sábado" in days_confirm

    # ainda não avançou pro objetivo
    assert onboarding_repo.load(PHONE)["step"] == "CONFIRM_DAYS"


def test_correction_at_confirm_days_updates_and_reasks(tmp_path):
    """No passo de confirmar os dias, reescrever os dias atualiza e pede
    confirmação de novo — não avança com o valor antigo."""

    conversation = FULL_CONVERSATION[:13] + [
        (
            "na verdade segunda, quarta e sexta",
            {"corrections": {"days": ["Monday", "Wednesday", "Friday"]}},
        ),
        ("agora sim", {"confirmed": True}),
        ("saúde", {"goal": "Saúde", "target_race": None,
                    "target_time": None}),
        ("sim", {"confirmed": True}),
    ]

    replies, _, profile_repo = _run_conversation(tmp_path, conversation)

    # eco inicial mostrava terça/sábado
    assert "terça-feira" in replies[12]

    # após a correção, reecoa já com os dias novos
    corrected_echo = replies[13]
    assert "Ajustei" in corrected_echo
    assert "segunda-feira" in corrected_echo
    assert "sexta-feira" in corrected_echo

    # perfil final sai com os dias corrigidos
    data = json.loads(
        (profile_repo.storage / "fulano.json").read_text(encoding="utf-8")
    )
    assert data["preferred_running_days"] == [
        "Monday", "Wednesday", "Friday",
    ]


def test_reject_at_confirm_days_reasks_days(tmp_path):
    """Dizer "não" na confirmação dos dias volta a perguntar os dias —
    não apaga o cadastro."""

    conversation = FULL_CONVERSATION[:13] + [
        ("não, tá errado", {"confirmed": False}),
    ]

    replies, onboarding_repo, _ = _run_conversation(tmp_path, conversation)

    assert "Quais dias" in replies[-1]
    assert onboarding_repo.load(PHONE)["step"] == "ASK_DAYS"


def test_confirm_days_correction_updates_and_reconfirms(tmp_path):
    """Atleta corrige os dias na conferência (bug do Adolfo): o cadastro
    NÃO é finalizado com os dias velhos — atualiza e reapresenta o resumo."""

    full_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    conversation = FULL_CONVERSATION[:-1] + [
        (
            "na verdade corro de segunda a sexta",
            {"corrections": {"days": full_week}},
        ),
        ("agora sim, pode montar", {"confirmed": True}),
    ]

    replies, onboarding_repo, profile_repo = _run_conversation(
        tmp_path,
        conversation,
    )

    # a resposta à correção reapresenta o resumo, já com a semana cheia
    correction_reply = replies[-2]
    assert "Corrigido" in correction_reply
    assert "segunda-feira" in correction_reply
    assert "sexta-feira" in correction_reply
    # ainda não finalizou: espera a confirmação
    assert "Cadastro feito" not in correction_reply

    # após confirmar, o perfil sai com os 5 dias corrigidos
    assert "Cadastro feito, Fulano" in replies[-1]

    data = json.loads(
        (profile_repo.storage / "fulano.json").read_text(encoding="utf-8")
    )
    assert data["preferred_running_days"] == full_week
    assert data["weekly_training_days"] == 5

    assert onboarding_repo.load(PHONE) is None


def test_confirm_field_correction_updates_then_finalizes(tmp_path):
    """Correção de um campo não-dia (peso e objetivo) na conferência:
    aplica, reapresenta o resumo e só finaliza com o dado novo."""

    conversation = FULL_CONVERSATION[:-1] + [
        (
            "na verdade meu peso é 130kg e quero maratona",
            {"corrections": {
                "weight": 130.0,
                "goal": "Maratona",
                "target_race": "42 km",
                "target_time": None,
            }},
        ),
        ("isso, pode montar", {"confirmed": True}),
    ]

    replies, onboarding_repo, profile_repo = _run_conversation(
        tmp_path,
        conversation,
    )

    # a correção reapresenta o resumo já com peso e objetivo novos
    correction_reply = replies[-2]
    assert "Corrigido" in correction_reply
    assert "130 kg" in correction_reply
    assert "Maratona" in correction_reply
    assert "Cadastro feito" not in correction_reply

    assert "Cadastro feito, Fulano" in replies[-1]

    data = json.loads(
        (profile_repo.storage / "fulano.json").read_text(encoding="utf-8")
    )
    assert data["weight"] == 130.0
    assert data["goal"] == "Maratona"
    assert data["target_race"] == "42 km"

    assert onboarding_repo.load(PHONE) is None


def test_invalid_correction_falls_back_to_confirm_question(tmp_path):
    """Correção fora de faixa (peso absurdo) é ignorada — não altera nem
    finaliza; pede confirmação de novo."""

    conversation = FULL_CONVERSATION[:-1] + [
        ("peso 999", {"corrections": {"weight": 999.0}}),
    ]

    replies, onboarding_repo, _ = _run_conversation(tmp_path, conversation)

    assert "Só confirmando" in replies[-1]
    # segue no CONFIRM, com o peso original intacto
    state = onboarding_repo.load(PHONE)
    assert state["step"] == "CONFIRM"
    assert state["answers"]["weight"] == 91.0


def test_decline_at_confirm_resets_onboarding(tmp_path):

    conversation = FULL_CONVERSATION[:-1] + [
        ("não", {"confirmed": False}),
    ]

    replies, onboarding_repo, profile_repo = _run_conversation(
        tmp_path,
        conversation,
    )

    assert "Sem problema" in replies[-1]
    assert onboarding_repo.load(PHONE) is None
    assert list(profile_repo.storage.glob("*.json")) == []


COACH_CONVERSATION_START = [
    ("oi", {}),
    ("Treinada", {"name": "Treinada"}),
    ("30", {"age": 30}),
    ("60kg", {"weight": 60.0}),
    ("1.60", {"height": 1.60}),
    ("tenho sim", {"has_strava": True}),
    ("sim", {"runs_today": True}),
    ("4x", {"runs_per_week": 4}),
    ("8km", {"typical_km": 8.0}),
    ("sim, tenho treinador", {"has_coach": True}),
    ("45 minutos", {"typical_minutes": 45.0}),
    (
        "terça, quinta, sábado e domingo",
        {"days": ["Tuesday", "Thursday", "Saturday", "Sunday"]},
    ),
    ("sim", {"confirmed": True}),
    ("maratona de SP", {"goal": "Maratona de SP",
                        "target_race": "42 km", "target_time": None}),
]

EXTRACTED_SESSIONS = [
    {"day": "Tuesday", "workout_type": "Intervalado",
     "distance_km": 8.0},
    {"day": "Saturday", "workout_type": "Longão",
     "distance_km": 16.0},
]


def test_coach_branch_receives_plan_media_and_finalizes(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.download_media") as mock_download,
        patch(f"{MODULE}.ExternalPlanExtractionEngine") as mock_engine,
        patch(f"{MODULE}.ExternalPlanService") as mock_service,
        patch(
            f"{MODULE}.WeeklyPlanMessageFormatter"
        ) as mock_formatter,
    ):

        mock_token_store.return_value.load.return_value = {"t": 1}

        mock_parser.parse = AsyncMock(
            side_effect=[p for _, p in COACH_CONVERSATION_START[1:]]
            + [{"confirmed": True}],
        )

        mock_download.return_value = (b"img", "image/jpeg")

        mock_engine.extract = AsyncMock(
            return_value=EXTRACTED_SESSIONS,
        )

        fake_plan = MagicMock()
        mock_service.apply.return_value = fake_plan

        mock_formatter.session_lines.return_value = [
            "terça: Intervalado 8 km",
        ]

        replies = [
            asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, text))
            for text, _ in COACH_CONVERSATION_START
        ]

        # depois do objetivo, pede o print do treino
        assert "print, foto ou PDF" in replies[-1]

        # mídia chega -> resumo com plano recebido
        media_reply = asyncio.run(
            OnboardingFlow.handle(
                "whatsapp",
                PHONE,
                "",
                media={"key_id": "M1", "mimetype": "image/jpeg"},
            )
        )

        assert "plano da semana recebido (2 treinos)" in media_reply
        # convida a mandar os outros dias antes de fechar
        assert "outros prints" in media_reply
        assert "registrar e acompanhar" in media_reply

        # confirmação final cria perfil external_coach e salva o plano
        final = asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, "sim"))

        assert "Plano do seu treinador registrado" in final

        data = json.loads(
            (profile_repo.storage / "treinada.json").read_text(
                encoding="utf-8",
            )
        )
        assert data["external_coach"] is True

        mock_service.apply.assert_called_once()
        args = mock_service.apply.call_args.args
        assert args[0] == "treinada"
        assert args[2] == EXTRACTED_SESSIONS


def test_coach_plan_accepts_multiple_prints(tmp_path):
    """Plano do treinador em vários prints (um por dia): todos os treinos
    entram, não só o primeiro (bug do onboarding do Mauricio)."""

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.download_media") as mock_download,
        patch(f"{MODULE}.ExternalPlanExtractionEngine") as mock_engine,
        patch(f"{MODULE}.ExternalPlanService") as mock_service,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
    ):

        mock_token_store.return_value.load.return_value = {"t": 1}

        mock_parser.parse = AsyncMock(
            side_effect=[p for _, p in COACH_CONVERSATION_START[1:]]
            + [{"confirmed": True}],
        )

        mock_download.return_value = (b"img", "image/jpeg")

        # cada print traz um dia diferente do plano
        mock_engine.extract = AsyncMock(
            side_effect=[
                [{"day": "Tuesday", "workout_type": "Intervalado",
                  "distance_km": 5.0}],
                [{"day": "Thursday", "workout_type": "HIIT",
                  "distance_km": 6.0}],
                [{"day": "Saturday", "workout_type": "Longão",
                  "distance_km": 10.0}],
            ],
        )

        mock_service.apply.return_value = MagicMock()
        mock_formatter.session_lines.return_value = ["linha"]

        for text, _ in COACH_CONVERSATION_START:
            asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, text))

        # três prints, um de cada vez
        first = asyncio.run(OnboardingFlow.handle(
            "whatsapp", PHONE, "", media={"key_id": "1"}))
        second = asyncio.run(OnboardingFlow.handle(
            "whatsapp", PHONE, "", media={"key_id": "2"}))
        third = asyncio.run(OnboardingFlow.handle(
            "whatsapp", PHONE, "", media={"key_id": "3"}))

        # primeiro print: resumo completo convidando a mandar mais
        assert "outros prints" in first
        # prints seguintes: confirmação leve com a contagem acumulada
        assert "2 treino" in second
        assert "3 treino" in third

        asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, "sim"))

        # o plano registrado tem os 3 dias (não só o primeiro)
        mock_service.apply.assert_called_once()
        sessions_arg = mock_service.apply.call_args.args[2]
        days = [s["day"] for s in sessions_arg]
        assert days == ["Tuesday", "Thursday", "Saturday"]


def test_coach_plan_resend_same_day_replaces(tmp_path):
    """Reenviar o print do mesmo dia substitui (não duplica) a sessão."""

    existing = [{"day": "Tuesday", "workout_type": "Rodagem",
                 "distance_km": 5.0}]
    incoming = [{"day": "Tuesday", "workout_type": "Intervalado",
                 "distance_km": 8.0}]

    merged = OnboardingFlow._merge_sessions(existing, incoming)

    assert merged == [{"day": "Tuesday", "workout_type": "Intervalado",
                       "distance_km": 8.0}]


def test_media_outside_plan_step_is_deferred(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
    ):

        asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, "oi"))

        reply = asyncio.run(
            OnboardingFlow.handle(
                "whatsapp",
                PHONE,
                "",
                media={"key_id": "M1", "mimetype": "image/jpeg"},
            )
        )

        assert "terminar seu cadastro" in reply
        assert "como você se chama" in reply


def test_skip_media_goes_to_confirm(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
    ):

        mock_parser.parse = AsyncMock(
            side_effect=[p for _, p in COACH_CONVERSATION_START[1:]]
            + [{"skip": True}],
        )

        for text, _ in COACH_CONVERSATION_START:
            asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, text))

        reply = asyncio.run(
            OnboardingFlow.handle("whatsapp", PHONE, "mando depois"),
        )

        assert "vai mandar o plano depois" in reply
        assert "Posso registrar seu cadastro" in reply


def test_parser_error_asks_to_resend_instead_of_crashing(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    with (
        patch(
            f"{MODULE}.OnboardingStateRepository",
            return_value=onboarding_repo,
        ),
        patch(
            f"{MODULE}.RunnerProfileRepository",
            return_value=profile_repo,
        ),
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
    ):

        # inicia o onboarding (sem parser)
        asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, "oi"))

        # Gemini fora do ar / rate limit na resposta seguinte
        mock_parser.parse = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"),
        )

        reply = asyncio.run(OnboardingFlow.handle("whatsapp", PHONE, "Fulano"))

        assert "manda sua última mensagem de novo" in reply

        # estado preservado no mesmo passo
        assert onboarding_repo.load(PHONE)["step"] == "ASK_NAME"


def test_slug_collision_gets_numeric_suffix(tmp_path):

    onboarding_repo, profile_repo = _repos(tmp_path)

    # já existe um "fulano"
    (profile_repo.storage / "fulano.json").write_text(
        json.dumps({
            "id": "fulano", "name": "Fulano", "age": 30,
            "weight": 70.0, "height": 1.75, "phone": "551188",
            "goal": "5k", "weekly_training_days": 3,
        }),
        encoding="utf-8",
    )

    with patch(
        f"{MODULE}.RunnerProfileRepository",
        return_value=profile_repo,
    ):

        assert OnboardingFlow._unique_slug("Fulano") == "fulano2"
        assert OnboardingFlow._unique_slug("José da Silva") == "josedasilva"
