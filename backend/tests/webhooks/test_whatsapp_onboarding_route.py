from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

MODULE = "app.presentation.api.v1.webhooks"


def _payload(text: str = "oi") -> dict:

    return {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "5511900000000@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Fulano",
            "message": {"conversation": text},
        },
    }


def test_unknown_phone_starts_onboarding():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
    ):

        mock_repo_cls.return_value.find_by_phone.return_value = None

        mock_onboarding.execute = AsyncMock(
            return_value="Oi! Como você se chama?",
        )

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_payload(),
        )

        body = response.json()

        assert body["success"] is True
        assert body["onboarding"] is True

        mock_onboarding.execute.assert_awaited_once_with(
            channel="whatsapp",
            address="5511900000000",
            incoming_text="oi",
            sender_name="Fulano",
            media=None,
        )

        mock_coach.execute.assert_not_called()


def test_known_phone_goes_to_coach_conversation():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
    ):

        mock_repo_cls.return_value.find_by_phone.return_value = "renato"

        mock_coach.execute = AsyncMock(return_value="Bom dia!")

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_payload("bom dia coach"),
        )

        body = response.json()

        assert body["success"] is True
        assert body["profile"] == "renato"

        mock_onboarding.execute.assert_not_called()
