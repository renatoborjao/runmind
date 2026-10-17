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


def test_warm_up_loads_the_model_in_the_background(monkeypatch):
    """O boot aquece o modelo numa thread (1º áudio pós-restart não espera ~20 s)
    e erro no aquecimento nunca derruba nada."""

    import threading

    loaded = threading.Event()

    monkeypatch.setattr(
        VoiceTranscriber, "_get_model", staticmethod(lambda: loaded.set())
    )

    VoiceTranscriber.warm_up()

    assert loaded.wait(timeout=2)


def test_warm_up_swallows_load_errors(monkeypatch):

    import threading

    called = threading.Event()

    def boom():

        called.set()

        raise RuntimeError("sem rede pro modelo")

    monkeypatch.setattr(VoiceTranscriber, "_get_model", staticmethod(boom))

    VoiceTranscriber.warm_up()  # não pode levantar

    assert called.wait(timeout=2)
