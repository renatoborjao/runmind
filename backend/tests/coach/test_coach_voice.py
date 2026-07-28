import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.voice.coach_voice import CoachVoice
from tests.coach.factories import make_runner

MODULE = "app.application.coach.voice.coach_voice"


def _tg_runner():
    return make_runner(channel="telegram", telegram_id="42")


def _voice_only(runner, synth_return=b"oggbytes"):
    with (
        patch(f"{MODULE}.SpeechSynthesizer") as synth,
        patch(f"{MODULE}.TelegramService") as tg,
    ):

        synth.synthesize = AsyncMock(return_value=synth_return)
        tg.send_voice = AsyncMock()

        asyncio.run(
            CoachVoice.voice_only(runner, "É *hoje*! 🏁 Sua prova chegou.")
        )

        return synth, tg


def test_sends_voice_on_telegram():

    synth, tg = _voice_only(_tg_runner())

    synth.synthesize.assert_awaited_once()
    tg.send_voice.assert_awaited_once()
    assert tg.send_voice.await_args.args[1] == b"oggbytes"


def test_synthesis_failure_sends_nothing():

    synth, tg = _voice_only(_tg_runner(), synth_return=None)

    synth.synthesize.assert_awaited_once()
    tg.send_voice.assert_not_awaited()


def test_send_voice_failure_never_crashes():

    with (
        patch(f"{MODULE}.SpeechSynthesizer") as synth,
        patch(f"{MODULE}.TelegramService") as tg,
    ):

        synth.synthesize = AsyncMock(return_value=b"ogg")
        tg.send_voice = AsyncMock(side_effect=RuntimeError("telegram down"))

        # não levanta: áudio é best-effort (o texto já saiu por outro caminho)
        asyncio.run(CoachVoice.voice_only(_tg_runner(), "oi"))


def test_non_telegram_channel_does_not_synthesize():

    runner = make_runner(channel="whatsapp", telegram_id=None)

    synth, tg = _voice_only(runner)

    synth.synthesize.assert_not_awaited()
    tg.send_voice.assert_not_awaited()


def test_speakable_strips_markdown_emoji_and_bullets():

    spoken = CoachVoice._speakable(
        "É **hoje**! 🏁🔥\n\n• Largada controlada\n• Confia no plano 💪",
    )

    assert "*" not in spoken
    assert "🏁" not in spoken and "🔥" not in spoken and "💪" not in spoken
    assert "•" not in spoken
    assert "hoje" in spoken
    assert "Largada controlada" in spoken
