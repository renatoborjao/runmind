import asyncio
from unittest.mock import AsyncMock, patch

from app.application.notifications.notification_service import (
    NotificationService,
)
from tests.coach.factories import make_runner

MODULE = "app.application.notifications.notification_service"


def test_send_uses_whatsapp_for_whatsapp_channel():

    runner = make_runner(
        channel="whatsapp",
        phone="+5511999999999",
    )

    with (
        patch(f"{MODULE}.WhatsAppService") as mock_wa,
        patch(f"{MODULE}.TelegramService") as mock_tg,
    ):

        mock_wa.send_message = AsyncMock()
        mock_tg.send_message = AsyncMock()

        asyncio.run(NotificationService.send(runner, "oi"))

        mock_wa.send_message.assert_awaited_once_with(
            phone="+5511999999999",
            message="oi",
        )
        mock_tg.send_message.assert_not_called()


def test_send_uses_telegram_for_telegram_channel():

    runner = make_runner(
        channel="telegram",
        telegram_id="4242",
    )

    with (
        patch(f"{MODULE}.WhatsAppService") as mock_wa,
        patch(f"{MODULE}.TelegramService") as mock_tg,
    ):

        mock_wa.send_message = AsyncMock()
        mock_tg.send_message = AsyncMock()

        asyncio.run(NotificationService.send(runner, "bora"))

        mock_tg.send_message.assert_awaited_once_with(
            chat_id="4242",
            message="bora",
        )
        mock_wa.send_message.assert_not_called()


def test_send_to_routes_by_explicit_channel():

    with (
        patch(f"{MODULE}.WhatsAppService") as mock_wa,
        patch(f"{MODULE}.TelegramService") as mock_tg,
    ):

        mock_wa.send_message = AsyncMock()
        mock_tg.send_message = AsyncMock()

        asyncio.run(
            NotificationService.send_to("telegram", "999", "oi")
        )

        mock_tg.send_message.assert_awaited_once_with(
            chat_id="999",
            message="oi",
        )
        mock_wa.send_message.assert_not_called()
