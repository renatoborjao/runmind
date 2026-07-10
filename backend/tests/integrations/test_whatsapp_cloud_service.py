import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.integrations.whatsapp_cloud.whatsapp_cloud_service import (
    WhatsAppCloudService,
)

MODULE = (
    "app.infrastructure.integrations.whatsapp_cloud."
    "whatsapp_cloud_service"
)


def _settings():

    s = MagicMock()
    s.whatsapp_graph_version = "v21.0"
    s.whatsapp_phone_number_id = "1231540546707955"
    s.whatsapp_cloud_token = "TESTTOKEN"
    return s


def _capture_post():
    """Cliente httpx fake que guarda url/headers/json do post."""

    captured = {}

    async def fake_post(url, headers=None, json=None):

        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json

        return MagicMock(
            status_code=200,
            text='{"messages":[{"id":"wamid.X"}]}',
            json=lambda: {"messages": [{"id": "wamid.X"}]},
            raise_for_status=lambda: None,
        )

    client = MagicMock()
    client.__aenter__.return_value.post = AsyncMock(side_effect=fake_post)

    return client, captured


def test_send_message_builds_graph_text_payload():

    client, captured = _capture_post()

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings()),
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
    ):

        asyncio.run(
            WhatsAppCloudService.send_message("5511976483800", "Bora correr!")
        )

    assert "1231540546707955/messages" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer TESTTOKEN"

    body = captured["json"]
    assert body["to"] == "5511976483800"
    assert body["type"] == "text"
    assert body["text"]["body"] == "Bora correr!"


def test_send_message_strips_markdown():

    client, captured = _capture_post()

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings()),
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
    ):

        asyncio.run(
            WhatsAppCloudService.send_message("5511999", "**Parabéns**")
        )

    # markdown do Gemini não vai cru pro WhatsApp
    assert "**" not in captured["json"]["text"]["body"]


def test_send_template_builds_template_payload():

    client, captured = _capture_post()

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings()),
        patch(f"{MODULE}.httpx.AsyncClient", return_value=client),
    ):

        asyncio.run(
            WhatsAppCloudService.send_template(
                "5511999",
                "lembrete_treino",
                body_params=["Renato", "corrida leve 5km"],
            )
        )

    body = captured["json"]
    assert body["type"] == "template"
    assert body["template"]["name"] == "lembrete_treino"
    assert body["template"]["language"]["code"] == "pt_BR"

    params = body["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Renato", "corrida leve 5km"]
