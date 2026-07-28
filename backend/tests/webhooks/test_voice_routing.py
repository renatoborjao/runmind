import asyncio
from unittest.mock import AsyncMock, patch

from app.presentation.api.v1 import webhooks

MODULE = "app.presentation.api.v1.webhooks"


def _run_voice(voice: dict):
    """Roda o _run_inbound com uma nota de voz, mockando download +
    transcrição + roteamento. Devolve o mock de route_inbound e o de
    TelegramService pra checar o que aconteceu."""

    with (
        patch(f"{MODULE}.TelegramMediaClient") as media,
        patch(f"{MODULE}.VoiceTranscriber") as trans,
        patch(f"{MODULE}.TelegramService") as tg,
        patch(f"{MODULE}.route_inbound", new=AsyncMock()) as route,
    ):

        media.download = AsyncMock(return_value=(b"oggbytes", "audio/ogg"))
        trans.transcribe = AsyncMock(return_value="corri 8k tava pesado")
        tg.send_message = AsyncMock()

        asyncio.run(
            webhooks._run_inbound(
                channel="telegram",
                address="42",
                text=None,
                media=None,
                sender_name="Renato",
                voice=voice,
            )
        )

        return route, tg, trans


def test_voice_is_transcribed_and_flows_as_text():

    route, tg, _ = _run_voice({"file_id": "vid", "duration": 12})

    route.assert_awaited_once()
    assert route.await_args.kwargs["text"] == "corri 8k tava pesado"
    tg.send_message.assert_not_awaited()


def test_long_audio_asks_to_write_and_does_not_route():

    with (
        patch(f"{MODULE}.TelegramService") as tg,
        patch(f"{MODULE}.route_inbound", new=AsyncMock()) as route,
    ):

        tg.send_message = AsyncMock()

        asyncio.run(
            webhooks._run_inbound(
                channel="telegram",
                address="42",
                text=None,
                media=None,
                sender_name="R",
                voice={"file_id": "v", "duration": 99999},
            )
        )

        route.assert_not_awaited()
        tg.send_message.assert_awaited_once()
        assert "longo" in tg.send_message.await_args.args[1].lower()


def test_empty_transcription_asks_to_repeat():

    with (
        patch(f"{MODULE}.TelegramMediaClient") as media,
        patch(f"{MODULE}.VoiceTranscriber") as trans,
        patch(f"{MODULE}.TelegramService") as tg,
        patch(f"{MODULE}.route_inbound", new=AsyncMock()) as route,
    ):

        media.download = AsyncMock(return_value=(b"x", "audio/ogg"))
        trans.transcribe = AsyncMock(return_value="")
        tg.send_message = AsyncMock()

        asyncio.run(
            webhooks._run_inbound(
                channel="telegram",
                address="42",
                text=None,
                media=None,
                sender_name="R",
                voice={"file_id": "v", "duration": 5},
            )
        )

        route.assert_not_awaited()
        tg.send_message.assert_awaited_once()


def test_download_failure_never_becomes_silence():

    with (
        patch(f"{MODULE}.TelegramMediaClient") as media,
        patch(f"{MODULE}.TelegramService") as tg,
        patch(f"{MODULE}.route_inbound", new=AsyncMock()) as route,
    ):

        media.download = AsyncMock(side_effect=RuntimeError("boom"))
        tg.send_message = AsyncMock()

        asyncio.run(
            webhooks._run_inbound(
                channel="telegram",
                address="42",
                text=None,
                media=None,
                sender_name="R",
                voice={"file_id": "v", "duration": 5},
            )
        )

        route.assert_not_awaited()
        tg.send_message.assert_awaited_once()


def test_text_message_ignores_voice_path():
    """Mensagem de texto normal não passa por transcrição nenhuma."""

    with (
        patch(f"{MODULE}.VoiceTranscriber") as trans,
        patch(f"{MODULE}.route_inbound", new=AsyncMock()) as route,
    ):

        trans.transcribe = AsyncMock()

        asyncio.run(
            webhooks._run_inbound(
                channel="telegram",
                address="42",
                text="oi coach",
                media=None,
                sender_name="R",
                voice=None,
            )
        )

        trans.transcribe.assert_not_awaited()
        route.assert_awaited_once()
        assert route.await_args.kwargs["text"] == "oi coach"
