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
    ("33 anos, 91kg, 1,78", {"age": 33, "weight": 91.0, "height": 1.78}),
    ("não uso", {"has_strava": False}),
    (
        "corro 2x por semana, uns 5km",
        {"runs_today": True, "runs_per_week": 2, "typical_km": 5.0},
    ),
    ("não, treino por conta", {"has_coach": False}),
    ("uns 32 minutos", {"typical_minutes": 32.0}),
    ("terça e sábado", {"days": ["Tuesday", "Saturday"]}),
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


def test_full_onboarding_without_strava_creates_profile(tmp_path):

    replies, onboarding_repo, profile_repo = _run_conversation(
        tmp_path,
        FULL_CONVERSATION,
    )

    # primeira resposta dá boas-vindas e pede o nome
    assert "como você se chama" in replies[0]

    # sem conta no Strava: instrução de criar + link (obrigatório)
    assert "cria" in replies[3].lower()
    assert f"/api/v1/strava/connect?state=wa:{PHONE}" in replies[3]

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
        ("40, 80kg, 1.70", {"age": 40, "weight": 80.0, "height": 1.70}),
        ("uso sim", {"has_strava": True}),
        (
            "corro 3x, 6km",
            {"runs_today": True, "runs_per_week": 3, "typical_km": 6.0},
        ),
        ("não tenho treinador", {"has_coach": False}),
        # pace é perguntado mesmo com Strava (a conexão pode demorar)
        ("uns 40 minutos", {"typical_minutes": 40.0}),
        (
            "segunda, quarta e sexta",
            {"days": ["Monday", "Wednesday", "Friday"]},
        ),
        ("saúde", {"goal": "Saúde", "target_race": None,
                    "target_time": None}),
        ("sim", {"confirmed": True}),
    ]

    replies, _, profile_repo = _run_conversation(tmp_path, conversation)

    # link de conexão com state=telefone
    strava_reply = replies[3]
    assert f"/api/v1/strava/connect?state=wa:{PHONE}" in strava_reply

    # sequência: experiência -> treinador -> pace -> dias
    assert "já corre hoje" in strava_reply
    assert "treinador" in replies[4]
    assert "em quanto tempo" in replies[5]
    assert "Quais dias" in replies[6]

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
    ("30, 60kg, 1.60", {"age": 30, "weight": 60.0, "height": 1.60}),
    ("tenho sim", {"has_strava": True}),
    (
        "corro 4x, 8km",
        {"runs_today": True, "runs_per_week": 4, "typical_km": 8.0},
    ),
    ("sim, tenho treinador", {"has_coach": True}),
    ("45 minutos", {"typical_minutes": 45.0}),
    (
        "terça, quinta, sábado e domingo",
        {"days": ["Tuesday", "Thursday", "Saturday", "Sunday"]},
    ),
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
        assert "acompanhar os treinos" in media_reply

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
