"""Síntese de voz: texto do coach -> áudio OGG/OPUS pronto pra bolha de voz
do Telegram (sendVoice). Motor trocável por config: "gemini" (Gemini TTS, voz
Charon calorosa — escolhida em teste cego; o edge-tts grátis soou robótico) ou
"edge" (fallback grátis/externo).

A conversão pra OGG/OPUS usa o PyAV (que já vem com o faster-whisper e embute o
ffmpeg) — NADA de ffmpeg de sistema. Falha de síntese devolve None: o chamador
manda a mensagem em texto, nunca silêncio. Ver [[project_ideias_produto]]."""

import asyncio
import io
import wave

from app.core.config import get_settings

# o Opus opera em 48 kHz; as fontes (MP3 do edge a 24 kHz, PCM do Gemini a
# 24 kHz) são reamostradas antes de encodar
_OPUS_RATE = 48000

# o Gemini TTS devolve PCM cru mono 16-bit a 24 kHz
_GEMINI_PCM_RATE = 24000


class SpeechSynthesizer:

    @staticmethod
    async def synthesize(text: str) -> bytes | None:
        """Texto -> bytes de um OGG/OPUS. None quando o motor de voz falha
        (aí a mensagem sai só em texto). Best-effort de ponta a ponta."""

        if not text or not text.strip():

            return None

        settings = get_settings()

        try:

            # ponto de troca do motor
            if settings.voice_engine == "gemini":

                # Gemini TTS é síncrono (SDK) + a conversão é CPU-bound:
                # tudo numa thread pra não travar o event loop
                return await asyncio.to_thread(
                    SpeechSynthesizer._gemini_ogg, text,
                )

            # fallback: edge-tts
            mp3 = await SpeechSynthesizer._edge_mp3(
                text, settings.voice_edge_voice,
            )

            return await asyncio.to_thread(
                SpeechSynthesizer._to_ogg_opus, mp3,
            )

        except Exception as e:

            print(f"Síntese de voz falhou (motor={settings.voice_engine}): {e}")

            return None

    @staticmethod
    def _gemini_ogg(text: str) -> bytes:
        """Gemini TTS -> OGG/OPUS. O modelo devolve PCM cru 24 kHz mono; a
        gente embrulha em WAV e converte pra Opus (mesma conversão do edge)."""

        from google import genai
        from google.genai import types

        settings = get_settings()

        client = genai.Client(api_key=settings.google_api_key)

        response = client.models.generate_content(
            model=settings.voice_gemini_model,
            contents=settings.voice_gemini_style + text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=settings.voice_gemini_voice,
                        )
                    )
                ),
            ),
        )

        pcm = response.candidates[0].content.parts[0].inline_data.data

        if not pcm:

            raise RuntimeError("Gemini TTS não devolveu áudio")

        return SpeechSynthesizer._to_ogg_opus(
            SpeechSynthesizer._pcm_to_wav(pcm),
        )

    @staticmethod
    def _pcm_to_wav(pcm: bytes) -> bytes:
        """Embrulha o PCM cru do Gemini (mono 16-bit 24 kHz) num container
        WAV, pra o PyAV decodificar e reencodar em Opus."""

        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav:

            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(_GEMINI_PCM_RATE)
            wav.writeframes(pcm)

        return buffer.getvalue()

    @staticmethod
    async def _edge_mp3(text: str, voice: str) -> bytes:

        # import tardio: a lib só interessa quando o coach de fato fala
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)

        audio = bytearray()

        async for chunk in communicate.stream():

            if chunk["type"] == "audio":

                audio += chunk["data"]

        if not audio:

            raise RuntimeError("edge-tts não devolveu áudio")

        return bytes(audio)

    @staticmethod
    def _to_ogg_opus(mp3: bytes) -> bytes:
        """MP3 -> OGG/OPUS via PyAV (ffmpeg embutido). Reamostra pra 48 kHz
        mono, que é o que o encoder Opus exige."""

        import av
        from av.audio.resampler import AudioResampler

        input_container = av.open(io.BytesIO(mp3))

        output_buffer = io.BytesIO()
        output_container = av.open(output_buffer, mode="w", format="ogg")

        output_stream = output_container.add_stream("libopus", rate=_OPUS_RATE)

        resampler = AudioResampler(
            format="s16", layout="mono", rate=_OPUS_RATE,
        )

        for frame in input_container.decode(audio=0):

            frame.pts = None

            for resampled in resampler.resample(frame):

                for packet in output_stream.encode(resampled):

                    output_container.mux(packet)

        # drena o resampler e o encoder (últimos frames em buffer)
        for resampled in resampler.resample(None):

            for packet in output_stream.encode(resampled):

                output_container.mux(packet)

        for packet in output_stream.encode(None):

            output_container.mux(packet)

        output_container.close()
        input_container.close()

        return output_buffer.getvalue()
