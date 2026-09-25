"""Login próprio do app (sem depender de Telegram nem de e-mail): senha,
recuperação por link/código e Google — com convite pra conta nova."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.application.auth import password_auth_service as pas
from app.application.auth.google_auth_service import (
    GoogleAuthService,
    GoogleNeedsInvite,
)
from app.application.auth.password_auth_service import (
    LoginLocked,
    PasswordAuthService,
    PasswordError,
)
from app.infrastructure.persistence.credential_repository import (
    CredentialRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.security.password_hasher import (
    hash_password,
    verify_password,
)
from app.infrastructure.security.session_token import SessionToken
from app.main import app


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Perfis e credenciais num tmp; trava de força bruta zerada."""

    profiles = RunnerProfileRepository()
    profiles.storage = tmp_path / "profiles"
    profiles.storage.mkdir()

    creds = CredentialRepository()
    creds.storage = tmp_path / "creds"
    creds.storage.mkdir()

    for target in (
        "app.application.auth.password_auth_service",
        "app.application.auth.google_auth_service",
        "app.presentation.api.v1.auth",
    ):
        if hasattr(__import__(target, fromlist=["x"]), "CredentialRepository"):
            monkeypatch.setattr(f"{target}.CredentialRepository", lambda: creds)
        if hasattr(__import__(target, fromlist=["x"]), "RunnerProfileRepository"):
            monkeypatch.setattr(f"{target}.RunnerProfileRepository", lambda: profiles)

    monkeypatch.setattr(pas, "_failures", {})

    def add_profile(slug, email):
        (profiles.storage / f"{slug}.json").write_text(json.dumps({
            "id": slug, "name": slug.title(), "age": 30, "weight": 70.0,
            "height": 1.75, "phone": "", "goal": "10k",
            "weekly_training_days": 3, "email": email,
        }), encoding="utf-8")

    return profiles, creds, add_profile


# ------------------------------------------------------------- hash

def test_hash_roundtrip_and_salted():

    h1, h2 = hash_password("corrida123"), hash_password("corrida123")

    assert h1 != h2  # sal diferente
    assert verify_password("corrida123", h1)
    assert not verify_password("corrida124", h1)
    assert not verify_password("x", None)
    assert not verify_password("x", "lixo")


# ------------------------------------------------------------- senha

def test_login_with_password(env):

    _, _, add = env
    add("joana", "Joana@Mail.com")

    PasswordAuthService.set_password("joana", "senha-forte")

    assert PasswordAuthService.login("joana@mail.com ", "senha-forte") == "joana"
    assert PasswordAuthService.login("joana@mail.com", "errada") is None
    assert PasswordAuthService.login("ninguem@mail.com", "senha-forte") is None


def test_account_without_password_cannot_login_with_any_password(env):

    _, _, add = env
    add("joana", "joana@mail.com")

    assert PasswordAuthService.login("joana@mail.com", "") is None
    assert PasswordAuthService.login("joana@mail.com", "qualquer1") is None


def test_brute_force_locks_the_email(env):

    _, _, add = env
    add("joana", "joana@mail.com")
    PasswordAuthService.set_password("joana", "senha-forte")

    for _ in range(pas.MAX_FAILURES):
        assert PasswordAuthService.login("joana@mail.com", "chute") is None

    # travado: nem a senha certa entra agora
    with pytest.raises(LoginLocked):
        PasswordAuthService.login("joana@mail.com", "senha-forte")


def test_change_password_requires_current_but_first_does_not(env):

    _, _, add = env
    add("joana", "joana@mail.com")

    with pytest.raises(PasswordError):
        PasswordAuthService.set_password("joana", "curta")

    PasswordAuthService.set_password("joana", "primeira-senha")  # 1ª: sem atual

    with pytest.raises(PasswordError):
        PasswordAuthService.set_password("joana", "nova-senha-1", "errada")

    PasswordAuthService.set_password("joana", "nova-senha-1", "primeira-senha")

    assert PasswordAuthService.login("joana@mail.com", "nova-senha-1") == "joana"


def test_password_is_not_in_the_profile(env):

    profiles, creds, add = env
    add("joana", "joana@mail.com")

    PasswordAuthService.set_password("joana", "senha-forte")

    assert "senha" not in (profiles.storage / "joana.json").read_text("utf-8")
    assert creds.password_hash("joana").startswith("scrypt$")


# ------------------------------------------------------------- API

def test_api_login_sets_session_and_generic_error(env):

    _, _, add = env
    add("joana", "joana@mail.com")
    PasswordAuthService.set_password("joana", "senha-forte")

    client = TestClient(app)

    bad = client.post("/api/v1/auth/login", json={"email": "joana@mail.com", "password": "x"})
    ghost = client.post("/api/v1/auth/login", json={"email": "no@mail.com", "password": "x"})

    assert bad.status_code == ghost.status_code == 401
    assert bad.json() == ghost.json()  # não revela se a conta existe

    ok = client.post(
        "/api/v1/auth/login", json={"email": "joana@mail.com", "password": "senha-forte"},
    )

    assert ok.status_code == 200
    assert SessionToken.verify(ok.cookies.get("rm_session")) == "joana"


def test_api_reset_password_needs_reset_token_not_session(env):

    _, _, add = env
    add("joana", "joana@mail.com")
    PasswordAuthService.set_password("joana", "esqueci-essa")

    client = TestClient(app)

    session = SessionToken.issue("joana")

    denied = client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": session, "new_password": "nova-senha-1"},
    )

    assert denied.status_code == 400  # sessão não vale como permissão de reset

    reset = SessionToken.issue("joana", purpose="password_reset", ttl_seconds=60)

    ok = client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": reset, "new_password": "nova-senha-1"},
    )

    assert ok.status_code == 200
    assert PasswordAuthService.login("joana@mail.com", "nova-senha-1") == "joana"


def test_api_verify_link_returns_reset_token(env):

    _, _, add = env
    add("joana", "joana@mail.com")

    with patch(
        "app.presentation.api.v1.auth.MagicLinkService.verify",
        return_value=SessionToken.issue("joana"),
    ):

        r = TestClient(app).post("/api/v1/auth/verify", json={"token": "ABCDEF"})

    body = r.json()

    assert body["has_password"] is False
    assert SessionToken.verify(body["reset_token"], purpose="password_reset") == "joana"


def test_api_change_password_needs_login(env):

    _, _, add = env
    add("joana", "joana@mail.com")

    anon = TestClient(app).post("/api/v1/auth/password", json={"new_password": "nova-senha-1"})

    assert anon.status_code == 401

    client = TestClient(app)
    client.cookies.set("rm_session", SessionToken.issue("joana"))

    assert client.post(
        "/api/v1/auth/password", json={"new_password": "nova-senha-1"},
    ).status_code == 200

    me = client.get("/api/v1/auth/me").json()

    assert me["has_password"] is True
    assert me["google_linked"] is False


# ------------------------------------------------------------- Google

GOOGLE = {"sub": "g-123", "email": "joana@mail.com", "name": "Joana Silva"}

VERIFY = "app.application.auth.google_auth_service.verify_id_token"


def _run(coro):

    import asyncio

    return asyncio.run(coro)


def test_google_links_existing_account_by_verified_email(env):

    _, creds, add = env
    add("joana", "joana@mail.com")

    with patch(VERIFY, new=AsyncMock(return_value=GOOGLE)):

        first = _run(GoogleAuthService.authenticate("jwt"))

    assert first == {"profile": "joana", "created": False}
    assert creds.google_sub("joana") == "g-123"

    # depois, entra pelo Google mesmo se o e-mail do perfil mudar
    with patch(VERIFY, new=AsyncMock(return_value={**GOOGLE, "email": "outro@mail.com"})):

        again = _run(GoogleAuthService.authenticate("jwt"))

    assert again["profile"] == "joana"


def test_google_new_account_needs_invite(env):

    with patch(VERIFY, new=AsyncMock(return_value=GOOGLE)):

        with pytest.raises(GoogleNeedsInvite):
            _run(GoogleAuthService.authenticate("jwt"))


def test_google_new_account_with_invite_creates_and_links(env):

    profiles, creds, _ = env

    with (
        patch(VERIFY, new=AsyncMock(return_value=GOOGLE)),
        patch("app.application.auth.signup_service.RunnerProfileRepository", return_value=profiles),
        patch("app.application.auth.signup_service.InviteCodeRepository") as invites,
        patch("app.application.auth.signup_service.SignupService._send_code"),
    ):

        invites.return_value.validate.return_value = True

        result = _run(GoogleAuthService.authenticate("jwt", "RIT-1234"))

    assert result["created"] is True

    slug = result["profile"]

    assert creds.google_sub(slug) == "g-123"
    assert json.loads((profiles.storage / f"{slug}.json").read_text("utf-8"))["name"] == "Joana Silva"
    invites.return_value.consume.assert_called_once_with("RIT-1234")


def test_google_endpoint_answers_needs_invite_without_session(env):

    with patch(VERIFY, new=AsyncMock(return_value=GOOGLE)):

        r = TestClient(app).post("/api/v1/auth/google", json={"credential": "jwt"})

    assert r.json() == {"ok": False, "needs_invite": True}
    assert "rm_session" not in r.cookies


def test_google_token_checks_audience(monkeypatch):
    """Token de OUTRO app (aud diferente) não entra."""

    from app.application.auth import google_auth_service as gas

    monkeypatch.setattr(
        gas, "get_settings", lambda: type("S", (), {"google_client_id": "nosso-id"})(),
    )

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"aud": "outro-app", "iss": "accounts.google.com",
                    "email_verified": "true", "email": "a@b.com", "sub": "1"}

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return Resp()

    monkeypatch.setattr(gas.httpx, "AsyncClient", Client)

    with pytest.raises(gas.GoogleAuthError):
        _run(gas.verify_id_token("jwt"))


def test_signup_with_short_password_does_not_burn_invite(env):

    profiles, _, _ = env

    with (
        patch("app.application.auth.signup_service.RunnerProfileRepository", return_value=profiles),
        patch("app.application.auth.signup_service.InviteCodeRepository") as invites,
    ):

        invites.return_value.validate.return_value = True

        r = TestClient(app).post(
            "/api/v1/auth/signup",
            json={"email": "nova@mail.com", "invite_code": "RIT-1", "password": "123"},
        )

    assert r.status_code == 400
    invites.return_value.consume.assert_not_called()
