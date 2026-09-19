from fastapi.testclient import TestClient

from app.infrastructure.security.session_token import SessionToken
from app.main import app

client = TestClient(app)


def test_request_login_is_always_generic():
    """Não revela se o e-mail existe (anti-enumeração)."""

    r = client.post("/api/v1/auth/request", json={"email": "qualquer@x.com"})

    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_verify_with_bad_token_is_rejected():

    r = client.post("/api/v1/auth/verify", json={"token": "invalido"})

    assert r.status_code == 400


def test_me_without_cookie_is_401():

    r = client.get("/api/v1/auth/me")

    assert r.status_code == 401


def test_plan_route_is_protected():
    """A rota de plano agora exige sessão — sem cookie, 401 (não vaza plano de
    ninguém por ?profile=)."""

    r = client.get("/api/v1/plan?profile=renato2")

    assert r.status_code == 401


def test_me_with_valid_cookie_returns_profile(monkeypatch):

    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.presentation.api.v1.auth.RunnerProfileRepository",
        lambda: SimpleNamespace(
            load=lambda p: SimpleNamespace(
                name="Renato", email="a@b.com", goal="10k",
                onboarding_complete=True,
            )
        ),
    )

    session = SessionToken.issue("renato2")

    r = client.get(
        "/api/v1/auth/me",
        cookies={"rm_session": session},
    )

    assert r.status_code == 200
    assert r.json()["profile"] == "renato2"
