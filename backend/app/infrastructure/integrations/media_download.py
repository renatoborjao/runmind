from app.infrastructure.integrations.evolution.media_client import (
    EvolutionMediaClient,
)
from app.infrastructure.integrations.telegram.telegram_media_client import (
    TelegramMediaClient,
)
from app.infrastructure.integrations.whatsapp_cloud.whatsapp_cloud_media_client import (
    WhatsAppCloudMediaClient,
)


async def download_media(
    channel: str,
    media: dict,
) -> tuple[bytes, str]:
    """Baixa a mídia recebida pela fonte certa. O dict traz o id nativo,
    e a CHAVE dele identifica a origem (self-describing): `file_id` no
    Telegram, `media_id` na Cloud API, `key_id` na Evolution. Casar pela
    chave — e não só pelo canal — separa os dois drivers de WhatsApp, que
    compartilham channel="whatsapp"."""

    if "file_id" in media:

        return await TelegramMediaClient.download(media["file_id"])

    if "media_id" in media:

        return await WhatsAppCloudMediaClient.download(media["media_id"])

    return await EvolutionMediaClient.download(media["key_id"])
