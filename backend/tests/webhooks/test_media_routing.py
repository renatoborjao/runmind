from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.integrations.evolution.inbound_parser import (
    WhatsAppInboundParser,
)
from tests.coach.factories import make_runner

MODULE = "app.presentation.api.v1.webhooks"


def _media_payload(mimetype: str = "image/jpeg") -> dict:

    return {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "5511900000000@s.whatsapp.net",
                "fromMe": False,
                "id": "MSGID123",
            },
            "pushName": "Fulano",
            "message": {
                "imageMessage": {
                    "mimetype": mimetype,
                    "caption": "treino da semana",
                },
            },
        },
    }


def test_extract_media_detects_supported_image():

    media = WhatsAppInboundParser.extract_media(
        _media_payload()["data"],
    )

    assert media == {
        "key_id": "MSGID123",
        "mimetype": "image/jpeg",
        "caption": "treino da semana",
    }


def test_extract_media_rejects_unsupported_mimetype():

    media = WhatsAppInboundParser.extract_media(
        _media_payload(mimetype="video/mp4")["data"],
    )

    assert media is None


def test_extract_media_returns_none_for_plain_text():

    assert WhatsAppInboundParser.extract_media(
        {"message": {"conversation": "oi"}},
    ) is None


def test_media_from_external_coach_athlete_triggers_plan_event():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.ExternalPlanEvent") as mock_event,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_phone.return_value = "fulano"
        mock_repo.load.return_value = make_runner(external_coach=True)

        mock_event.execute = AsyncMock(return_value="registrado")

        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_media_payload(),
        )

        assert response.json()["queued"] is True

        mock_event.execute.assert_awaited_once_with(
            profile="fulano",
            media={
                "key_id": "MSGID123",
                "mimetype": "image/jpeg",
                "caption": "treino da semana",
            },
        )

        mock_coach.execute.assert_not_called()


def test_media_from_regular_athlete_gets_polite_reply():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.ExternalPlanEvent") as mock_event,
        patch(f"{MODULE}.NotificationService") as mock_notification,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_phone.return_value = "renato"
        mock_repo.load.return_value = make_runner(external_coach=False)

        mock_notification.send = AsyncMock()

        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_media_payload(),
        )

        assert response.json()["queued"] is True

        mock_event.execute.assert_not_called()

        assert "treinador" in mock_notification.send.call_args.args[1]
