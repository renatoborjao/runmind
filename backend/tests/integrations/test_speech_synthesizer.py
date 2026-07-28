import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.integrations.audio.speech_synthesizer import (
    SpeechSynthesizer,
)

MODULE = "app.infrastructure.integrations.audio.speech_synthesizer"


def _settings(engine="gemini"):
    s = MagicMock()
    s.voice_engine = engine
    s.voice_edge_voice = "pt-BR-AntonioNeural"
    return s


def test_empty_text_returns_none():

    assert asyncio.run(SpeechSynthesizer.synthesize("")) is None
    assert asyncio.run(SpeechSynthesizer.synthesize("   ")) is None


def test_gemini_engine_routes_to_gemini():

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings("gemini")),
        patch.object(
            SpeechSynthesizer, "_gemini_ogg", return_value=b"ogg-bytes",
        ) as gemini,
    ):

        out = asyncio.run(SpeechSynthesizer.synthesize("bom dia"))

    assert out == b"ogg-bytes"
    gemini.assert_called_once()


def test_edge_engine_routes_to_edge():

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings("edge")),
        patch.object(
            SpeechSynthesizer,
            "_edge_mp3",
            new=AsyncMock(return_value=b"mp3"),
        ),
        patch.object(
            SpeechSynthesizer, "_to_ogg_opus", return_value=b"ogg-from-edge",
        ),
    ):

        out = asyncio.run(SpeechSynthesizer.synthesize("oi"))

    assert out == b"ogg-from-edge"


def test_synthesis_failure_returns_none():

    with (
        patch(f"{MODULE}.get_settings", return_value=_settings("gemini")),
        patch.object(
            SpeechSynthesizer,
            "_gemini_ogg",
            side_effect=RuntimeError("gemini fora"),
        ),
    ):

        assert asyncio.run(SpeechSynthesizer.synthesize("oi")) is None
