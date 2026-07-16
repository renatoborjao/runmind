from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.application.events.coach_conversation import CoachUnavailable
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


def _post(update, secret_header=None, is_new=True):

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_telegram_id.return_value = None

        mock_onboarding.execute = AsyncMock(return_value="oi!")
        mock_coach.execute = AsyncMock(return_value="resposta")

        # is_new=False simula uma reentrega do mesmo update pelo Telegram
        mock_guard_cls.return_value.check_and_mark.return_value = is_new

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

    assert response.json()["queued"] is True

    # o processamento roda em background (o TestClient o executa antes de
    # devolver a resposta), então o roteamento é observável
    mock_onboarding.execute.assert_awaited_once_with(
        channel="telegram",
        address="42",
        incoming_text="oi",
        sender_name="Novo",
        media=None,
        send_fallback=False,
    )
    mock_coach.execute.assert_not_called()


def test_duplicate_update_is_ignored():
    """Reentrega do mesmo update_id não pode rodar o pipeline de novo —
    é o que multiplicava o "me embananei" na cara do atleta."""

    response, mock_onboarding, mock_coach, _ = _post(
        _update(), secret_header="s3cr3t", is_new=False,
    )

    assert response.json()["ignored"] is True
    assert response.json()["reason"] == "duplicate update"

    mock_onboarding.execute.assert_not_called()
    mock_coach.execute.assert_not_called()


def test_known_chat_goes_to_coach():

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"

        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_telegram_id.return_value = "renato"

        mock_coach.execute = AsyncMock(return_value="resposta")

        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_update("como foi meu treino?"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )

        assert response.json()["queued"] is True
        mock_coach.execute.assert_awaited_once()


def test_coach_unavailable_triggers_deferred_retry():
    """Gemini indisponível não vira "me embananei" na hora: o webhook
    espera e tenta de novo; a resposta real chega na tentativa seguinte."""

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEvent") as mock_coach,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"
        mock_repo_cls.return_value.find_by_telegram_id.return_value = "renato"
        mock_guard_cls.return_value.check_and_mark.return_value = True

        # indisponível 2x, acerta na 3ª (a real chega, sem fallback)
        mock_coach.execute = AsyncMock(
            side_effect=[
                CoachUnavailable("429"),
                CoachUnavailable("429"),
                "resposta real",
            ],
        )

        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_update("como diminuir a FC?"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )

        assert response.json()["queued"] is True

        # tentou 3 vezes e esperou entre as tentativas
        assert mock_coach.execute.await_count == 3
        assert mock_sleep.await_count == 2

        # tentativas intermediárias sem fallback; a última libera o fallback
        assert (
            mock_coach.execute.await_args_list[0].kwargs["send_fallback"]
            is False
        )
        assert (
            mock_coach.execute.await_args_list[-1].kwargs["send_fallback"]
            is True
        )


def test_onboarding_unavailable_triggers_deferred_retry():
    """Mesma blindagem vale pro cadastro: Gemini fora no onboarding é
    adiado, não vira "me embananei" de imediato."""

    from app.application.events.assistant_errors import AssistantUnavailable

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.OnboardingEvent") as mock_onboarding,
        patch(f"{MODULE}.ProcessedInboundGuard") as mock_guard_cls,
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):

        mock_settings.return_value.telegram_webhook_secret = "s3cr3t"
        mock_repo_cls.return_value.find_by_telegram_id.return_value = None
        mock_guard_cls.return_value.check_and_mark.return_value = True

        mock_onboarding.execute = AsyncMock(
            side_effect=[
                AssistantUnavailable("429"),
                "Oi! Como você se chama?",
            ],
        )

        client = TestClient(app)
        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_update("oi"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )

        assert response.json()["queued"] is True
        assert mock_onboarding.execute.await_count == 2
        assert mock_sleep.await_count == 1
        assert (
            mock_onboarding.execute.await_args_list[0].kwargs["send_fallback"]
            is False
        )


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
