import asyncio
from unittest.mock import MagicMock, patch

from app.infrastructure.notifications.whatsapp_service import (
    WhatsAppService,
)

MODULE = "app.infrastructure.notifications.whatsapp_service"


def test_send_is_skipped_when_whatsapp_disabled():
    """WHATSAPP_ENABLED=false (Evolution desligada): não abre cliente
    HTTP nenhum — nada de traceback a cada envio agendado."""

    settings = MagicMock()
    settings.whatsapp_enabled = False

    with (
        patch(f"{MODULE}.get_settings", return_value=settings),
        patch(f"{MODULE}.httpx.AsyncClient") as mock_client,
    ):

        result = asyncio.run(
            WhatsAppService.send_message("5511999999999", "oi")
        )

        assert result is None

        mock_client.assert_not_called()
