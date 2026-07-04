from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from tests.coach.factories import make_runner

MODULE = "app.presentation.api.v1.webhooks"


def _update(text: str = "oi") -> dict:

    return {
        "update_id": 1,
        "message": {
            "message_id": 5,
            "from": {"id": 42, "is_bot": False, "first_name": "Novo"},
            "chat": {"id": 42, "type": "private"},
            "text": text,
        },
    }


def _post(update, secret_header=None):

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_telegram_id.return_value = None

        mock_onboarding.execute = AsyncMock(return_value="oi!")
        mock_coach.execute = AsyncMock(return_value="resposta")

        headers = {}
        if secret_header is not None:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret_header

        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/telegram",
            json=update,
            headers=headers,
        )

        return response, mock_onboarding, mock_coach, mock_repo


def test_unknown_chat_starts_onboarding_on_telegram():

    response, mock_onboarding, mock_coach, _ = _post(
        _update(), secret_header="s3cr3t",
    )

    assert response.json()["onboarding"] is True

    mock_onboarding.execute.assert_awaited_once_with(
        channel="telegram",
        address="42",
        incoming_text="oi",
        sender_name="Novo",
        media=None,
    )
    mock_coach.execute.assert_not_called()


def test_known_chat_goes_to_coach():

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_telegram_id.return_value = "renato"

        mock_coach.execute = AsyncMock(return_value="resposta")

        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_update("como foi meu treino?"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )

        assert response.json()["profile"] == "renato"
        mock_coach.execute.assert_awaited_once()


def test_wrong_secret_is_rejected():

    response, _, _, _ = _post(_update(), secret_header="errado")

    assert response.status_code == 401


def test_bot_message_is_ignored():

    update = _update()
    update["message"]["from"]["is_bot"] = True

    response, mock_onboarding, _, _ = _post(
        update, secret_header="s3cr3t",
    )

    assert response.json()["ignored"] is True
    mock_onboarding.execute.assert_not_called()
