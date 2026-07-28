import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.infrastructure.integrations.audio.voice_transcriber import (
    VoiceTranscriber,
)


def test_joins_segments_into_clean_text():

    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [
            SimpleNamespace(text=" corri 8k "),
            SimpleNamespace(text=" tava pesado no fim "),
        ],
        None,
    )

    with patch.object(
        VoiceTranscriber, "_get_model", return_value=fake_model,
    ):

        text = asyncio.run(VoiceTranscriber.transcribe(b"oggbytes"))

    assert text == "corri 8k tava pesado no fim"


def test_empty_audio_returns_empty_string():

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([], None)

    with patch.object(
        VoiceTranscriber, "_get_model", return_value=fake_model,
    ):

        assert asyncio.run(VoiceTranscriber.transcribe(b"x")) == ""
