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


def test_callback_without_state_returns_400(tmp_path):
    """Sem state não dá pra saber de quem é o callback. Antes caía num perfil
    fixo ("renato"), o que num app multi-atleta gravaria tokens no dono errado;
    agora rejeita, igual a um cadastro não encontrado."""

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
            params={"code": "abc"},
        )

        assert response.status_code == 400


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


# ----------------------------------------------------------------------
# Atleta do APP (self-cadastro): state = "app:<volta>:<token assinado>"
# ----------------------------------------------------------------------

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.security.session_token import SessionToken  # noqa: E402


def _write_app_profile(profile_repo, slug, onboarding_complete=True):

    (profile_repo.storage / f"{slug}.json").write_text(
        json.dumps({
            "id": slug, "name": "App", "age": 30,
            "weight": 70.0, "height": 1.75, "goal": "10k",
            "weekly_training_days": 3, "channel": "app", "phone": "",
            "onboarding_complete": onboarding_complete,
        }),
        encoding="utf-8",
    )


def _app_state(slug, back="perfil", ttl=600):

    token = SessionToken.issue(
        slug, purpose="strava_connect", ttl_seconds=ttl,
    )

    return f"app:{back}:{token}"


def _app_callback(profile_repo, onboarding_repo, params):

    with (
        patch(f"{MODULE}.httpx.AsyncClient",
              return_value=_mock_token_exchange()),
        patch(f"{MODULE}.RunnerProfileRepository",
              return_value=profile_repo),
        patch(f"{MODULE}.OnboardingStateRepository",
              return_value=onboarding_repo),
        patch(f"{MODULE}.TokenStore") as mock_token_store_cls,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_history,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
        patch(f"{MODULE}.StravaConnectRefresh") as mock_refresh,
    ):

        mock_history.execute = AsyncMock()
        mock_records.seed = AsyncMock()
        mock_refresh.refresh = AsyncMock()

        client = TestClient(app)

        response = client.get(
            "/api/v1/strava/callback",
            params=params,
            follow_redirects=False,
        )

        return response, mock_token_store_cls, mock_history, mock_refresh


def test_app_callback_connects_and_redirects_back_to_profile(tmp_path):

    profile_repo, onboarding_repo = _repos(tmp_path)

    _write_app_profile(profile_repo, "joana")

    response, tokens, history, refresh = _app_callback(
        profile_repo, onboarding_repo,
        {"code": "abc", "state": _app_state("joana")},
    )

    base = get_settings().app_base_url.rstrip("/")

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{base}/perfil?strava=ok"

    tokens.assert_called_once_with("joana")

    # cadastro concluído = late connector: regenera o plano com o histórico
    refresh.refresh.assert_awaited_once_with("joana")
    history.execute.assert_not_awaited()

    data = json.loads((profile_repo.storage / "joana.json").read_text("utf-8"))
    assert data["strava_athlete_id"] == 777


def test_app_callback_mid_onboarding_only_loads_history(tmp_path):
    """Conectou no passo do cadastro (perfil-esqueleto): NÃO gera plano ainda
    (sai na conclusão, já com o histórico) — volta pro wizard."""

    profile_repo, onboarding_repo = _repos(tmp_path)

    _write_app_profile(profile_repo, "novata", onboarding_complete=False)

    response, tokens, history, refresh = _app_callback(
        profile_repo, onboarding_repo,
        {"code": "abc", "state": _app_state("novata", back="onboarding")},
    )

    assert response.headers["location"].endswith("/onboarding?strava=ok")

    tokens.assert_called_once_with("novata")
    refresh.refresh.assert_not_awaited()
    history.execute.assert_awaited_once_with(profile="novata")

    data = json.loads((profile_repo.storage / "novata.json").read_text("utf-8"))
    assert data["strava_athlete_id"] == 777


def test_app_callback_with_forged_or_expired_token_saves_nothing(tmp_path):

    profile_repo, onboarding_repo = _repos(tmp_path)

    _write_app_profile(profile_repo, "joana")

    session = SessionToken.issue("joana")  # sessão NÃO vale como state

    for state in (
        f"app:perfil:{session}",
        _app_state("joana", ttl=-1),
        "app:perfil:lixo.lixo",
        _app_state("fantasma"),  # perfil inexistente
    ):

        response, tokens, _, refresh = _app_callback(
            profile_repo, onboarding_repo, {"code": "abc", "state": state},
        )

        assert response.headers["location"].endswith("/perfil?strava=erro")
        tokens.assert_not_called()
        refresh.refresh.assert_not_awaited()


def test_app_callback_denied_on_strava_redirects_with_error(tmp_path):
    """Atleta clicou "Cancelar" no Strava: vem `error=access_denied`, sem code."""

    profile_repo, onboarding_repo = _repos(tmp_path)

    _write_app_profile(profile_repo, "joana")

    response, tokens, _, _ = _app_callback(
        profile_repo, onboarding_repo,
        {"error": "access_denied", "state": _app_state("joana")},
    )

    assert response.headers["location"].endswith("/perfil?strava=erro")
    tokens.assert_not_called()


def test_app_connect_requires_session_and_scopes_the_state():

    client = TestClient(app)

    # sem sessão: volta pro login do app
    response = client.get(
        "/api/v1/strava/app-connect", follow_redirects=False,
    )

    assert response.headers["location"].endswith("/entrar")

    # com sessão: manda pro Strava com state de uso restrito (não a sessão)
    session = SessionToken.issue("joana")

    client.cookies.set(get_settings().auth_cookie_name, session)

    response = client.get(
        "/api/v1/strava/app-connect",
        params={"back": "onboarding"},
        follow_redirects=False,
    )

    location = response.headers["location"]

    assert location.startswith("https://www.strava.com/oauth/authorize")

    state = location.split("state=", 1)[1]

    assert state.startswith("app:onboarding:")
    assert session not in state

    token = state[len("app:onboarding:"):]

    assert SessionToken.verify(token, purpose="strava_connect") == "joana"
    assert SessionToken.verify(token) is None

    # volta fora da lista fechada vira "perfil" (nada de redirect aberto)
    response = client.get(
        "/api/v1/strava/app-connect",
        params={"back": "https://evil.example"},
        follow_redirects=False,
    )

    assert "state=app:perfil:" in response.headers["location"]
