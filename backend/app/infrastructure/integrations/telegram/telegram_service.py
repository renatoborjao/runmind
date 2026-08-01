import asyncio

import httpx

from app.core.config import get_settings
from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)

# Uma resposta que engasga no ENVIO não pode virar silêncio (a reativa não
# tem reentrega, diferente da proativa) — ver [[feedback_conversa_viva]]. Um
# blip de rede / 5xx / 429 é transitório: repetimos com recuo. 4xx (fora do
# 429), tipo chat_id inválido, é pedido malformado: repetir não conserta.
_SEND_MAX_ATTEMPTS = 3

_SEND_BACKOFF_SECONDS = 2


class TelegramService:

    @staticmethod
    async def _call(
        endpoint: str,
        *,
        timeout: int,
        label: str,
        **post_kwargs,
    ):
        """POST na API do Telegram com retry em falha TRANSITÓRIA (rede,
        timeout, 5xx, 429). 4xx não-429 sobe na hora — retry não conserta
        pedido inválido. Só levanta depois de esgotar as tentativas."""

        settings = get_settings()

        url = (
            f"https://api.telegram.org/bot"
            f"{settings.telegram_bot_token}/{endpoint}"
        )

        last_exc: Exception | None = None

        for attempt in range(1, _SEND_MAX_ATTEMPTS + 1):

            try:

                async with httpx.AsyncClient(timeout=timeout) as client:

                    response = await client.post(url, **post_kwargs)

                print(f"==== {label} ====")
                print("STATUS:", response.status_code, f"(tentativa {attempt})")
                print(response.text[:300])
                print("==================")

                response.raise_for_status()

                return response.json()

            except httpx.HTTPStatusError as e:

                status = e.response.status_code

                # 4xx (menos 429) = pedido inválido: repetir não ajuda
                if 400 <= status < 500 and status != 429:

                    raise

                last_exc = e

            except httpx.HTTPError as e:   # rede / timeout / transporte

                last_exc = e

            if attempt < _SEND_MAX_ATTEMPTS:

                await asyncio.sleep(_SEND_BACKOFF_SECONDS * attempt)

        raise last_exc   # esgotou as tentativas — deixa o chamador decidir

    @staticmethod
    async def send_message(
        chat_id: str,
        message: str,
    ):

        # Telegram não renderiza o markdown do Gemini sem parse_mode;
        # normalizamos para texto limpo (sem "**", bullets viram "•").
        message = to_plain_text(message)

        return await TelegramService._call(
            "sendMessage",
            timeout=30,
            label="TELEGRAM",
            json={
                "chat_id": chat_id,
                "text": message,
            },
        )

    @staticmethod
    async def send_voice(
        chat_id: str,
        audio: bytes,
        caption: str = "",
    ):
        """Manda uma nota de voz (bolha de áudio, não 'arquivo de música').
        `audio` precisa ser OGG/OPUS — o SpeechSynthesizer entrega assim."""

        data = {"chat_id": chat_id}

        if caption:

            # legenda do Telegram tem teto de 1024 chars
            data["caption"] = to_plain_text(caption)[:1024]

        files = {"voice": ("coach.ogg", audio, "audio/ogg")}

        return await TelegramService._call(
            "sendVoice",
            timeout=60,
            label="TELEGRAM VOICE",
            data=data,
            files=files,
        )
