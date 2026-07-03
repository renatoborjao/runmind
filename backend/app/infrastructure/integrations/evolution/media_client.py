import base64

import httpx

from app.core.config import get_settings


class EvolutionMediaClient:
    """Baixa o conteúdo de uma mídia recebida (imagem/PDF) pela
    Evolution API."""

    @staticmethod
    async def download(
        key_id: str,
    ) -> tuple[bytes, str]:
        """Retorna (bytes, mimetype) da mídia da mensagem `key_id`."""

        settings = get_settings()

        async with httpx.AsyncClient(timeout=60) as client:

            response = await client.post(
                f"{settings.evolution_api_url}"
                f"/chat/getBase64FromMediaMessage"
                f"/{settings.evolution_instance}",
                headers={
                    "apikey": settings.evolution_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "message": {
                        "key": {"id": key_id},
                    },
                    "convertToMp4": False,
                },
            )

            response.raise_for_status()

            data = response.json()

        raw = data["base64"]

        # pode vir como data URI ("data:image/jpeg;base64,....")
        if "," in raw and raw.startswith("data:"):

            raw = raw.split(",", 1)[1]

        return (
            base64.b64decode(raw),
            data.get("mimetype", "application/octet-stream"),
        )
