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
                "id": "MSG1",
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
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_repo_cls.return_value.find_by_phone.return_value = None

        mock_onboarding.execute = AsyncMock(
            return_value="Oi! Como você se chama?",
        )

        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_payload(),
        )

        assert response.json()["queued"] is True

        # processamento em background (rodado pelo TestClient)
        mock_onboarding.execute.assert_awaited_once_with(
            channel="whatsapp",
            address="5511900000000",
            incoming_text="oi",
            sender_name="Fulano",
            media=None,
            send_fallback=False,
        )

        mock_coach.execute.assert_not_called()


def test_known_phone_goes_to_coach_conversation():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_repo_cls.return_value.find_by_phone.return_value = "renato"

        mock_coach.execute = AsyncMock(return_value="Bom dia!")

        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_payload("bom dia coach"),
        )

        assert response.json()["queued"] is True

        mock_coach.execute.assert_awaited_once()
        mock_onboarding.execute.assert_not_called()


def test_duplicate_message_is_ignored():
    """Reentrega da mesma mensagem pela Evolution não pode reprocessar."""

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_repo_cls.return_value.find_by_phone.return_value = "renato"
        mock_coach.execute = AsyncMock(return_value="Bom dia!")

        mock_guard_cls.return_value.check_and_mark.return_value = False

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_payload("bom dia coach"),
        )

        assert response.json()["ignored"] is True
        mock_coach.execute.assert_not_called()
        mock_onboarding.execute.assert_not_called()
