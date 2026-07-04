from app.infrastructure.integrations.evolution.media_client import (
    EvolutionMediaClient,
)
from app.infrastructure.integrations.telegram.telegram_media_client import (
    TelegramMediaClient,
)


async def download_media(
    channel: str,
    media: dict,
) -> tuple[bytes, str]:
    """Baixa a mídia recebida pelo canal certo. O dict de mídia traz
    `mimetype` e o id nativo (`key_id` no WhatsApp, `file_id` no
    Telegram)."""

    if channel == "telegram":

        return await TelegramMediaClient.download(media["file_id"])

    return await EvolutionMediaClient.download(media["key_id"])
