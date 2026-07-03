import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.application.onboarding.onboarding_flow import OnboardingFlow
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MODULE = "app.application.onboarding.onboarding_flow"

PHONE = "5511900000000"


def _repos(tmp_path):

    onboarding_repo = OnboardingStateRepository()
    onboarding_repo.storage = tmp_path / "onboarding"
    onboarding_repo.storage.mkdir()

    profile_repo = RunnerProfileRepository()
    profile_repo.storage = tmp_path / "profiles"
    profile_repo.storage.mkdir()

    return onboarding_repo, profile_repo


def _run_conversation(tmp_path, exchanges):
    """exchanges: lista de (texto_do_corredor, resposta_do_parser).
    Retorna as respostas do bot."""

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
                    OnboardingFlow.handle(PHONE, text),
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
    assert f"/api/v1/strava/connect?state={PHONE}" in replies[3]

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
    assert f"/api/v1/strava/connect?state={PHONE}" in strava_reply

    # pergunta seguinte é a de experiência, depois pace, depois dias
    assert "já corre hoje" in strava_reply
    assert "em quanto tempo" in replies[4]
    assert "Quais dias" in replies[5]

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
            asyncio.run(OnboardingFlow.handle(PHONE, text))
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
        asyncio.run(OnboardingFlow.handle(PHONE, "oi"))

        # Gemini fora do ar / rate limit na resposta seguinte
        mock_parser.parse = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"),
        )

        reply = asyncio.run(OnboardingFlow.handle(PHONE, "Fulano"))

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
