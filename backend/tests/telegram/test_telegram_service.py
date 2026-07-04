import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.integrations.telegram.telegram_service import (
    TelegramService,
)

MODULE = "app.infrastructure.integrations.telegram.telegram_service"


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
