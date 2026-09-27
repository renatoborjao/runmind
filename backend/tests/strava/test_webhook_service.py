import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.services.strava.webhook_service import WebhookService

MOD = "app.application.services.strava.webhook_service"

NEW = "https://runmind.duckdns.org/api/v1/webhooks/strava"
OLD = "https://unopened-employed-cedar.ngrok-free.dev/api/v1/webhooks/strava"


def test_delete_sends_id_in_path():
    """O Strava exige /push_subscriptions/{id} — query param dava 500."""

    response = MagicMock()
    http = MagicMock()
    http.delete = AsyncMock(return_value=response)
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=False)

    settings = SimpleNamespace(strava_client_id="1", strava_client_secret="s")

    with (
        patch(f"{MOD}.httpx.AsyncClient", return_value=http),
        patch(f"{MOD}.get_settings", return_value=settings),
    ):

        asyncio.run(WebhookService.delete(359610))

    url = http.delete.await_args.args[0]
    params = http.delete.await_args.kwargs["params"]

    assert url.endswith("/push_subscriptions/359610")
    assert "id" not in params


def _repoint(current):

    with (
        patch.object(WebhookService, "subscriptions",
                     AsyncMock(return_value=current)),
        patch.object(WebhookService, "delete", AsyncMock()) as delete,
        patch.object(WebhookService, "register",
                     AsyncMock(return_value={"id": 2})) as register,
    ):

        result = asyncio.run(WebhookService.repoint(NEW))

    return result, delete, register


def test_repoint_replaces_stale_subscription():
    """O caso da migração: inscrição no ngrok velho -> apaga e cria a nova."""

    result, delete, register = _repoint([{"id": 1, "callback_url": OLD}])

    delete.assert_awaited_once_with(1)
    register.assert_awaited_once_with(NEW)
    assert result["changed"] is True


def test_repoint_is_noop_when_already_correct():

    result, delete, register = _repoint([{"id": 2, "callback_url": NEW}])

    delete.assert_not_awaited()
    register.assert_not_awaited()
    assert result["changed"] is False


def test_repoint_creates_when_none_exists():

    result, delete, register = _repoint([])

    delete.assert_not_awaited()
    register.assert_awaited_once_with(NEW)
