"""Transcrição de voz LOCAL: nota de áudio do atleta -> texto, via
faster-whisper (Whisper da OpenAI, MIT) rodando em CPU/ARM. Grátis e
self-hosted — o áudio nunca sai da máquina. O texto transcrito entra no
MESMO pipeline de conversa que o coach já entende (RPE, aversão, treino
avulso, estratégia de prova...). Ver [[project_ideias_produto]]."""

import asyncio
import io

from app.core.config import get_settings

# O modelo é carregado UMA vez (o primeiro uso baixa os pesos pro cache do
# HuggingFace); recarregar a cada áudio seria caríssimo. None até o 1º uso.
_model = None


class VoiceTranscriber:

    @staticmethod
    async def transcribe(audio: bytes) -> str:
        """Bytes de um OGG/OPUS -> texto em pt-BR. String vazia quando não
        deu pra entender nada (áudio mudo/ruído). Roda o whisper (síncrono e
        CPU-bound) numa thread pra não travar o event loop do FastAPI."""

        return await asyncio.to_thread(
            VoiceTranscriber._transcribe_sync, audio,
        )

    @staticmethod
    def _transcribe_sync(audio: bytes) -> str:

        model = VoiceTranscriber._get_model()

        # faster-whisper decodifica o OGG direto (via PyAV embutido); não
        # precisa de ffmpeg de sistema pra ENTRADA
        segments, _info = model.transcribe(
            io.BytesIO(audio),
            language="pt",
        )

        return " ".join(
            segment.text.strip() for segment in segments
        ).strip()

    @staticmethod
    def _get_model():

        global _model

        if _model is None:

            # import tardio: a lib é pesada e só interessa quando alguém de
            # fato manda um áudio — não queremos pagar isso no boot
            from faster_whisper import WhisperModel

            settings = get_settings()

            _model = WhisperModel(
                settings.whisper_model,
                device="cpu",
                compute_type="int8",
            )

        return _model
