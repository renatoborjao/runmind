import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MODULE = "app.presentation.api.v1.strava"

TOKEN_RESPONSE = {
    "access_token": "at",
    "refresh_token": "rt",
    "expires_at": 123,
    "athlete": {"id": 777},
}


def _mock_token_exchange():
    """Mocka o POST https://www.strava.com/oauth/token."""

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = TOKEN_RESPONSE

    client = MagicMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    async def post(*args, **kwargs):
        return response

    client.post = post

    return client


def _repos(tmp_path):

    profile_repo = RunnerProfileRepository()
    profile_repo.storage = tmp_path / "profiles"
    profile_repo.storage.mkdir()

    onboarding_repo = OnboardingStateRepository()
    onboarding_repo.storage = tmp_path / "onboarding"
    onboarding_repo.storage.mkdir()

    return profile_repo, onboarding_repo


def test_callback_with_existing_profile_saves_tokens_and_athlete_id(
    tmp_path,
):

    profile_repo, onboarding_repo = _repos(tmp_path)

    (profile_repo.storage / "fulano.json").write_text(
        json.dumps({
            "id": "fulano", "name": "Fulano", "age": 30,
            "weight": 70.0, "height": 1.75,
            "phone": "5511900000000", "goal": "10k",
            "weekly_training_days": 3,
            "notifications": True,
        }),
        encoding="utf-8",
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore") as mock_token_store_cls,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_history,
        patch(f"{MODULE}.StravaConnectRefresh") as mock_refresh,
    ):

        mock_history.execute = AsyncMock()
        mock_refresh.refresh = AsyncMock()

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params={"code": "abc", "state": "5511900000000"},
        )

        body = response.json()

        assert body["saved"] is True
        assert body["profile"] == "fulano"

        # tokens no store do perfil certo
        mock_token_store_cls.assert_called_once_with("fulano")
        saved_tokens = mock_token_store_cls.return_value.save.call_args[0][0]
        assert saved_tokens["access_token"] == "at"

        # perfil já cadastrado (late connector): agenda o refresh do plano
        # com o histórico real — não carrega histórico inline no callback
        mock_refresh.refresh.assert_awaited_once_with("fulano")
        mock_history.execute.assert_not_awaited()

        # athlete_id persistido, chaves extras preservadas
        data = json.loads(
            (profile_repo.storage / "fulano.json").read_text(
                encoding="utf-8",
            )
        )
        assert data["strava_athlete_id"] == 777
        assert data["notifications"] is True


def test_callback_during_onboarding_stashes_athlete_id_in_state(
    tmp_path,
):

    profile_repo, onboarding_repo = _repos(tmp_path)

    onboarding_repo.save(
        "5511900000000",
        {"step": "ASK_DAYS", "answers": {}, "slug": "ciclano"},
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore") as mock_token_store_cls,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_history,
        patch(f"{MODULE}.StravaConnectRefresh") as mock_refresh,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
    ):

        mock_history.execute = AsyncMock()
        mock_refresh.refresh = AsyncMock()
        mock_records.seed = AsyncMock()

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params={"code": "abc", "state": "5511900000000"},
        )

        assert response.json()["profile"] == "ciclano"

        # tokens já ficam no slug reservado
        mock_token_store_cls.assert_called_once_with("ciclano")

        # onboarding em andamento: arquiva o histórico aqui; o plano é
        # montado na conclusão do cadastro, então NÃO agenda refresh
        mock_history.execute.assert_awaited_once_with(profile="ciclano")
        mock_refresh.refresh.assert_not_awaited()

        # semeia os recordes já aqui (o slug é o profile.id final)
        mock_records.seed.assert_awaited_once_with("ciclano")

        # athlete_id guardado no estado (vai pro perfil na conclusão)
        state = onboarding_repo.load("5511900000000")
        assert state["strava_athlete_id"] == 777


def test_callback_without_state_keeps_renato_behavior(tmp_path):

    profile_repo, onboarding_repo = _repos(tmp_path)

    (profile_repo.storage / "renato.json").write_text(
        json.dumps({
            "id": "renato", "name": "Renato", "age": 33,
            "weight": 91.0, "height": 1.78,
            "phone": "5511975658679", "goal": "10k",
            "weekly_training_days": 3,
        }),
        encoding="utf-8",
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore") as mock_token_store_cls,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_history,
        patch(f"{MODULE}.StravaConnectRefresh") as mock_refresh,
    ):

        mock_history.execute = AsyncMock()
        mock_refresh.refresh = AsyncMock()

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params={"code": "abc"},
        )

        assert response.json()["profile"] == "renato"

        mock_token_store_cls.assert_called_once_with("renato")

        # sem state = perfil renato (source profile): agenda o refresh
        mock_refresh.refresh.assert_awaited_once_with("renato")


def test_callback_with_unknown_state_returns_400(tmp_path):

    profile_repo, onboarding_repo = _repos(tmp_path)

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore"),
    ):

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params={"code": "abc", "state": "5599999999999"},
        )

        assert response.status_code == 400


def test_callback_with_telegram_state_resolves_by_chat_id(tmp_path):

    profile_repo, onboarding_repo = _repos(tmp_path)

    (profile_repo.storage / "tonho.json").write_text(
        json.dumps({
            "id": "tonho", "name": "Tonho", "age": 30,
            "weight": 70.0, "height": 1.75,
            "phone": "", "channel": "telegram", "telegram_id": "4242",
            "goal": "10k", "weekly_training_days": 3,
        }),
        encoding="utf-8",
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore") as mock_token_store_cls,
        patch(f"{MODULE}.StravaConnectRefresh") as mock_refresh,
    ):

        mock_refresh.refresh = AsyncMock()

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params={"code": "abc", "state": "tg:4242"},
        )

        assert response.json()["profile"] == "tonho"
        mock_token_store_cls.assert_called_once_with("tonho")

        # perfil por telegram_id (source profile): agenda o refresh do plano
        mock_refresh.refresh.assert_awaited_once_with("tonho")

        data = json.loads(
            (profile_repo.storage / "tonho.json").read_text("utf-8")
        )
        assert data["strava_athlete_id"] == 777
