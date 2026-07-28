from unittest.mock import patch

from app.application.coach.voice.voice_preference_flow import (
    VoicePreferenceFlow,
)

MODULE = "app.application.coach.voice.voice_preference_flow"


def test_detect_off_variants():

    assert VoicePreferenceFlow.detect("prefiro sem áudio") is False
    assert VoicePreferenceFlow.detect("para de mandar áudio") is False
    assert VoicePreferenceFlow.detect("pode mandar só texto, sem voz") is False
    assert VoicePreferenceFlow.detect("prefiro texto") is False


def test_detect_on_variants():

    assert VoicePreferenceFlow.detect("pode voltar a mandar áudio") is True
    assert VoicePreferenceFlow.detect("adoro os áudios, manda mais") is True
    assert VoicePreferenceFlow.detect("quero receber em voz de novo") is True


def test_detect_ignores_unrelated():

    assert VoicePreferenceFlow.detect("corri 8k hoje") is None
    assert VoicePreferenceFlow.detect("qual meu treino de amanhã?") is None
    assert VoicePreferenceFlow.detect("") is None


def test_handle_sets_off_and_confirms():

    with patch(f"{MODULE}.VoicePreferenceRepository") as repo:

        reply = VoicePreferenceFlow.handle("renato2", "prefiro sem áudio")

        assert reply is not None
        assert "escrito" in reply.lower()
        repo.set.assert_called_once_with("renato2", False)


def test_handle_sets_on_and_confirms():

    with patch(f"{MODULE}.VoicePreferenceRepository") as repo:

        reply = VoicePreferenceFlow.handle("renato2", "pode mandar áudio de novo")

        assert reply is not None
        repo.set.assert_called_once_with("renato2", True)


def test_handle_returns_none_when_unrelated():

    with patch(f"{MODULE}.VoicePreferenceRepository") as repo:

        assert VoicePreferenceFlow.handle("renato2", "corri 8k") is None
        repo.set.assert_not_called()
