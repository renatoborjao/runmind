import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.integrations.strava.client import StravaClient

MODULE = "app.infrastructure.integrations.strava.client"


def _client_with_tokens(tokens: dict | None) -> StravaClient:

    client = StravaClient("helio")

    client.token_store = MagicMock()
    client.token_store.load.return_value = tokens

    return client


def test_reuses_cached_token_when_still_valid():

    client = _client_with_tokens({
        "access_token": "cached-token",
        "refresh_token": "refresh",
        "expires_at": time.time() + 3600,
    })

    with patch(f"{MODULE}.httpx.AsyncClient") as http_cls:

        token = asyncio.run(client._get_access_token())

    http_cls.assert_not_called()
    assert token == "cached-token"


def test_refreshes_when_token_close_to_expiry():

    client = _client_with_tokens({
        "access_token": "stale-token",
        "refresh_token": "refresh",
        "expires_at": time.time() + 60,
    })

    response = MagicMock()
    response.json.return_value = {
        "access_token": "fresh-token",
        "refresh_token": "new-refresh",
        "expires_at": time.time() + 21600,
    }

    http = AsyncMock()
    http.post.return_value = response
    http_ctx = MagicMock()
    http_ctx.__aenter__.return_value = http

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=http_ctx):

        token = asyncio.run(client._get_access_token())

    assert token == "fresh-token"
    client.token_store.save.assert_called_once()


def test_refreshes_when_no_expires_at_stored():

    client = _client_with_tokens({
        "access_token": "legacy-token",
        "refresh_token": "refresh",
    })

    response = MagicMock()
    response.json.return_value = {
        "access_token": "fresh-token",
        "refresh_token": "new-refresh",
        "expires_at": time.time() + 21600,
    }

    http = AsyncMock()
    http.post.return_value = response
    http_ctx = MagicMock()
    http_ctx.__aenter__.return_value = http

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=http_ctx):

        token = asyncio.run(client._get_access_token())

    assert token == "fresh-token"


def test_raises_when_no_token_saved():

    client = _client_with_tokens(None)

    with pytest.raises(Exception, match="Nenhum token encontrado"):

        asyncio.run(client._get_access_token())


def test_refresh_preserva_o_scope_salvo():
    """O refresh do Strava NÃO retorna o escopo — o save da renovação tem que
    preservar o scope que o callback gravou, senão a 1ª renovação apagaria o
    que sabíamos (e can_write voltaria a 'desconhecido')."""

    client = _client_with_tokens({
        "access_token": "stale-token",
        "refresh_token": "refresh",
        "expires_at": time.time() + 60,
        "scope": "read,activity:read_all,activity:write",
    })

    response = MagicMock()
    response.json.return_value = {
        "access_token": "fresh-token",
        "refresh_token": "new-refresh",
        "expires_at": time.time() + 21600,
    }

    http = AsyncMock()
    http.post.return_value = response
    http_ctx = MagicMock()
    http_ctx.__aenter__.return_value = http

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=http_ctx):

        asyncio.run(client._get_access_token())

    saved = client.token_store.save.call_args[0][0]

    assert saved["scope"] == "read,activity:read_all,activity:write"


def test_can_write_reflete_o_scope_concedido():
    """can_write: True com activity:write, False sem, None quando o scope é
    desconhecido (conectou antes de gravarmos) — pra distinguir 'não pode' de
    'precisa reconectar pra saber'."""

    cases = {
        None: None,                                              # sem token
        "read,activity:read_all,activity:write": True,
        "read,activity:read_all": False,
        "": None,                                                # scope vazio → desconhecido
    }

    for scope, expected in cases.items():

        tokens = None if scope is None else {"scope": scope}

        # scope "" cai no ramo de desconhecido (None) só se tratado assim;
        # aqui garantimos o contrato: "" e ausência => None
        with patch(f"{MODULE}.TokenStore") as TS:

            TS.return_value.load.return_value = tokens

            got = StravaClient.can_write("helio")

        assert got is expected, f"scope={scope!r}: {got} != {expected}"
