import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.integrations.evolution.connection_watchdog import (
    ConnectionWatchdog,
)

MODULE = (
    "app.infrastructure.integrations.evolution.connection_watchdog"
)


def _mock_http(state: str):

    state_response = MagicMock()
    state_response.json.return_value = {"instance": {"state": state}}
    state_response.raise_for_status.return_value = None

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=state_response)

    return client


def test_open_state_does_not_reconnect():

    client = _mock_http("open")

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=client):

        state = asyncio.run(ConnectionWatchdog.check_and_heal())

    assert state == "open"
    # só a checagem de estado, sem chamada de reconexão
    assert client.get.await_count == 1


def test_closed_state_triggers_reconnect():

    client = _mock_http("close")

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=client):

        state = asyncio.run(ConnectionWatchdog.check_and_heal())

    assert state == "close"

    assert client.get.await_count == 2
    reconnect_url = client.get.await_args_list[1].args[0]
    assert "/instance/connect/" in reconnect_url
