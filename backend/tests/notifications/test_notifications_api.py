from fastapi.testclient import TestClient

from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)
from app.infrastructure.persistence.push_subscription_repository import (
    PushSubscriptionRepository,
)
from app.infrastructure.security.session_token import SessionToken
from app.main import app

client = TestClient(app)

NMOD = "app.presentation.api.v1.notifications"


def _cookie() -> dict:

    return {"rm_session": SessionToken.issue("renato2")}


def _point_repos_at(monkeypatch, tmp_path):
    """Faz a API usar storage temporário (não polui os dados reais)."""

    def notif_factory():
        r = AppNotificationRepository()
        r.storage = tmp_path / "notif"
        r.storage.mkdir(parents=True, exist_ok=True)
        return r

    def push_factory():
        r = PushSubscriptionRepository()
        r.storage = tmp_path / "push"
        r.storage.mkdir(parents=True, exist_ok=True)
        return r

    monkeypatch.setattr(f"{NMOD}.AppNotificationRepository", notif_factory)
    monkeypatch.setattr(f"{NMOD}.PushSubscriptionRepository", push_factory)


def test_notifications_require_auth():

    assert client.get("/api/v1/notifications").status_code == 401


def test_list_and_mark_read(monkeypatch, tmp_path):

    _point_repos_at(monkeypatch, tmp_path)

    # semeia direto no repo temporário
    seed = AppNotificationRepository()
    seed.storage = tmp_path / "notif"
    seed.storage.mkdir(parents=True, exist_ok=True)
    seed.append("renato2", "treino de hoje", title="Seu treino de hoje")
    seed.append("renato2", "recorde!", title="Recorde")

    r = client.get("/api/v1/notifications", cookies=_cookie())
    assert r.status_code == 200
    body = r.json()
    assert body["unread"] == 2
    assert len(body["items"]) == 2

    r2 = client.post("/api/v1/notifications/read", json={}, cookies=_cookie())
    assert r2.status_code == 200
    assert r2.json()["unread"] == 0


def test_push_subscribe_and_unsubscribe(monkeypatch, tmp_path):

    _point_repos_at(monkeypatch, tmp_path)

    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}

    r = client.post("/api/v1/push/subscribe", json=sub, cookies=_cookie())
    assert r.status_code == 200
    assert r.json()["ok"] is True

    check = PushSubscriptionRepository()
    check.storage = tmp_path / "push"
    assert len(check.list("renato2")) == 1

    r2 = client.post(
        "/api/v1/push/unsubscribe",
        json={"endpoint": "https://push.example/abc"},
        cookies=_cookie(),
    )
    assert r2.status_code == 200
    assert check.list("renato2") == []


def test_public_key_endpoint_is_open():

    r = client.get("/api/v1/push/public-key")
    assert r.status_code == 200
    assert "key" in r.json()
