import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.notifications.whatsapp_service import (
    WhatsAppService,
)

MODULE = "app.infrastructure.notifications.whatsapp_service"


def _settings(provider: str, enabled: bool = True):

    s = MagicMock()
    s.whatsapp_enabled = enabled
    s.whatsapp_provider = provider
    return s


def test_cloud_provider_routes_to_cloud_service():

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings("cloud")),
        patch(f"{MODULE}.WhatsAppCloudService") as mock_cloud,
    ):

        mock_cloud.send_message = AsyncMock(return_value={"ok": True})

        asyncio.run(WhatsAppService.send_message("5511999", "oi"))

        mock_cloud.send_message.assert_awaited_once_with(
            phone="5511999",
            message="oi",
        )


def test_evolution_provider_does_not_touch_cloud():

    with (
        patch(
            f"{MODULE}.get_settings",
            return_value=_settings("evolution"),
        ),
        patch(f"{MODULE}.WhatsAppCloudService") as mock_cloud,
        patch(f"{MODULE}.httpx.AsyncClient") as mock_client,
    ):

        # cliente HTTP fake pra não bater na Evolution real
        ctx = mock_client.return_value.__aenter__.return_value
        ctx.post = AsyncMock(
            return_value=MagicMock(
                status_code=200,
                text="{}",
                json=lambda: {},
                raise_for_status=lambda: None,
            ),
        )

        asyncio.run(WhatsAppService.send_message("5511999", "oi"))

        mock_cloud.send_message.assert_not_called()


def test_disabled_skips_both_providers():

    with (
        patch(
            f"{MODULE}.get_settings",
            return_value=_settings("cloud", enabled=False),
        ),
        patch(f"{MODULE}.WhatsAppCloudService") as mock_cloud,
    ):

        result = asyncio.run(WhatsAppService.send_message("5511999", "oi"))

        assert result is None
        mock_cloud.send_message.assert_not_called()
