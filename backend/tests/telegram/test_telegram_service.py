import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.infrastructure.integrations.telegram.telegram_service import (
    TelegramService,
)

MODULE = "app.infrastructure.integrations.telegram.telegram_service"


def _ok_response():

    response = MagicMock()
    response.status_code = 200
    response.text = "{}"
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None
    return response


def _client_returning(*post_side_effect):
    """Cliente httpx dublado; cada item de `post_side_effect` é o retorno
    (ou exceção) de uma chamada consecutiva a `post`."""

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(side_effect=list(post_side_effect))
    return client


def test_send_message_posts_to_bot_api():

    response = MagicMock()
    response.status_code = 200
    response.text = "{}"
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=client):

        asyncio.run(
            TelegramService.send_message(
                chat_id="42",
                message="bom treino!",
            )
        )

    url = client.post.await_args.args[0]
    payload = client.post.await_args.kwargs["json"]

    assert url.endswith("/sendMessage")
    assert payload == {"chat_id": "42", "text": "bom treino!"}


def test_send_voice_posts_multipart_audio():

    response = MagicMock()
    response.status_code = 200
    response.text = "{}"
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)

    with patch(f"{MODULE}.httpx.AsyncClient", return_value=client):

        asyncio.run(
            TelegramService.send_voice(
                chat_id="42",
                audio=b"oggbytes",
            )
        )

    url = client.post.await_args.args[0]
    data = client.post.await_args.kwargs["data"]
    files = client.post.await_args.kwargs["files"]

    assert url.endswith("/sendVoice")
    assert data == {"chat_id": "42"}
    assert files["voice"][1] == b"oggbytes"
    assert files["voice"][2] == "audio/ogg"


def test_send_message_retries_transient_failure_then_succeeds():
    """Um blip de rede no envio não pode virar silêncio: repete e entrega."""

    client = _client_returning(
        httpx.ConnectError("blip de rede"),   # 1ª tentativa engasga
        _ok_response(),                        # 2ª tentativa entrega
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()),
    ):

        result = asyncio.run(
            TelegramService.send_message(chat_id="42", message="oi"),
        )

    assert result == {"ok": True}
    assert client.post.await_count == 2   # engasgou uma, entregou na outra


def test_send_message_gives_up_after_max_attempts():
    """Falha transitória persistente: tenta 3x e então levanta (o chamador
    decide o fallback) — melhor que silêncio, sem loop infinito."""

    client = _client_returning(
        httpx.ConnectError("caiu"),
        httpx.ConnectError("caiu"),
        httpx.ConnectError("caiu"),
    )

    with (
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()),
    ):

        with pytest.raises(httpx.HTTPError):

            asyncio.run(
                TelegramService.send_message(chat_id="42", message="oi"),
            )

    assert client.post.await_count == 3


def test_send_message_does_not_retry_on_4xx():
    """4xx (ex.: chat_id inválido) é pedido malformado — repetir não conserta,
    então sobe na primeira, sem gastar tentativas."""

    bad = MagicMock()
    bad.status_code = 400
    bad.text = "Bad Request: chat not found"
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=MagicMock(), response=bad,
    )

    client = _client_returning(bad)

    with (
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()) as sleep,
    ):

        with pytest.raises(httpx.HTTPStatusError):

            asyncio.run(
                TelegramService.send_message(chat_id="42", message="oi"),
            )

    assert client.post.await_count == 1   # não repetiu
    sleep.assert_not_awaited()
