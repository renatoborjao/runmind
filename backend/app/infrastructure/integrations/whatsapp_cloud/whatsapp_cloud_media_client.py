import httpx

from app.core.config import get_settings


class WhatsAppCloudMediaClient:
    """Baixa mídia da Cloud API. São dois passos: GET no media_id devolve
    uma URL temporária; GET nessa URL (com o mesmo bearer) devolve os
    bytes. Usado pra ler o plano do treinador externo em imagem/PDF."""

    @staticmethod
    async def download(
        media_id: str,
    ) -> tuple[bytes, str]:

        settings = get_settings()

        headers = {
            "Authorization": f"Bearer {settings.whatsapp_cloud_token}",
        }

        base = (
            f"https://graph.facebook.com/"
            f"{settings.whatsapp_graph_version}"
        )

        async with httpx.AsyncClient(timeout=30) as client:

            meta = await client.get(
                f"{base}/{media_id}",
                headers=headers,
            )

            meta.raise_for_status()

            info = meta.json()

            url = info["url"]

            mimetype = (info.get("mime_type") or "").split(";")[0]

            # a URL da mídia também exige o bearer
            binary = await client.get(url, headers=headers)

            binary.raise_for_status()

            return binary.content, mimetype
