import json

from fastapi.testclient import TestClient

from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.security.session_token import SessionToken
from app.main import app

client = TestClient(app)

CMOD = "app.presentation.api.v1.coach"


def _cookie():
    return {"rm_session": SessionToken.issue("renato2")}


def test_coach_timeline_merges_chat_and_proactive(monkeypatch, tmp_path):
    """A aba Coach junta a conversa E os proativos (análise/lembrete), em ordem,
    e cada proativo traz kind/title/url (atalho pra tela certa)."""

    conv_dir = tmp_path / "conv"
    conv_dir.mkdir()
    notif_dir = tmp_path / "notif"
    notif_dir.mkdir()

    # conversa: um turno às 10:00 UTC
    (conv_dir / "renato2.json").write_text(
        json.dumps([{"role": "user", "text": "oi coach", "timestamp": "2026-09-14T10:00:00+00:00"}]),
        encoding="utf-8",
    )

    # proativo: lembrete do dia às 09:00 BRT (= 12:00 UTC, DEPOIS do turno)
    (notif_dir / "renato2.json").write_text(
        json.dumps([{
            "id": "n1", "kind": "daily_training", "title": "Seu treino de hoje",
            "text": "Hoje: Intervalado 4x1km", "created_at": "2026-09-14T09:00:00-03:00",
            "read": False,
        }]),
        encoding="utf-8",
    )

    def conv_factory():
        r = ConversationRepository()
        r.storage = conv_dir
        return r

    def notif_factory():
        r = AppNotificationRepository()
        r.storage = notif_dir
        return r

    monkeypatch.setattr(f"{CMOD}.ConversationRepository", conv_factory)
    monkeypatch.setattr(f"{CMOD}.AppNotificationRepository", notif_factory)

    r = client.get("/api/v1/coach/messages", cookies=_cookie())
    assert r.status_code == 200

    msgs = r.json()["messages"]
    assert len(msgs) == 2

    # ordem cronológica: turno (10h UTC) antes do proativo (12h UTC)
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "coach"

    push = msgs[1]
    assert push["kind"] == "daily_training"
    assert push["title"] == "Seu treino de hoje"
    assert push["url"] == "/treino/detalhe/"


def test_coach_timeline_requires_auth():
    assert client.get("/api/v1/coach/messages").status_code == 401
