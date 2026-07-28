"""Liga/desliga os áudios proativos do coach por conversa: "prefiro sem
áudio" / "pode voltar a mandar em voz". Detector barato (palavra-chave), sem
Gemini — roda cedo no fluxo de conversa e grava a preferência dinâmica.
Ver [[project_ideias_produto]]."""

import re

from app.infrastructure.persistence.voice_preference_repository import (
    VoicePreferenceRepository,
)

# pista de que a mensagem fala sobre áudio/voz do coach
_AUDIO_CUE = re.compile(r"\b(áudio|audio|áudios|audios|voz|vozes)\b", re.I)

# pista de que o atleta quer TEXTO ("prefiro texto", "manda por escrito")
_TEXT_CUE = re.compile(r"\b(texto|escrit\w+|escrever|digit\w+)\b", re.I)

# quer PARAR de receber áudio
_OFF = re.compile(
    r"\b(sem|para|pare|parar|chega|nada de|não\s+man\w*|nao\s+man\w*|"
    r"prefiro|prefiro só|só|somente|apenas)\b",
    re.I,
)

# quer VOLTAR a receber áudio
_ON = re.compile(
    r"\b(pode|volta|voltar|manda|mande|quero|gosto|adoro|de novo|"
    r"novamente)\b",
    re.I,
)


class VoicePreferenceFlow:

    @staticmethod
    def detect(text: str) -> bool | None:
        """True = quer áudio, False = só texto, None = não é sobre isso."""

        if not text:

            return None

        has_audio = bool(_AUDIO_CUE.search(text))

        wants_text = bool(_TEXT_CUE.search(text))

        # não fala nem de áudio/voz nem de texto: não é sobre isso
        if not has_audio and not wants_text:

            return None

        # verbo explícito sobre o áudio decide primeiro (áudio ganha do texto
        # em frases como "não quero texto, manda áudio")
        if has_audio:

            if _OFF.search(text):

                return False

            if _ON.search(text):

                return True

        # sem verbo claro no áudio, mas pediu texto/escrito ("prefiro texto")
        if wants_text:

            return False

        return None

    @staticmethod
    def handle(profile: str, text: str) -> str | None:
        """Aplica a preferência e devolve a confirmação, ou None se a
        mensagem não é sobre áudio."""

        wants = VoicePreferenceFlow.detect(text)

        if wants is None:

            return None

        VoicePreferenceRepository.set(profile, wants)

        if wants:

            return (
                "Fechado! Voltei a te mandar os áudios nos momentos "
                "importantes. 🎙️ Quando quiser só texto, é só falar."
            )

        return (
            "Beleza, sem áudios da minha parte — sigo te mandando tudo "
            "por escrito. 📝 Se mudar de ideia, é só pedir que eu volto a "
            "falar. 😉"
        )
