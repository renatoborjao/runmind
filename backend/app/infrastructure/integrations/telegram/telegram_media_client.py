import httpx

from app.core.config import get_settings


class TelegramMediaClient:
    """Baixa mídia (foto/PDF) recebida pelo Telegram: getFile revela o
    caminho, depois baixa o binário."""

    @staticmethod
    async def download(
        file_id: str,
    ) -> tuple[bytes, str]:

        settings = get_settings()

        token = settings.telegram_bot_token

        async with httpx.AsyncClient(timeout=60) as client:

            info = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            )

            info.raise_for_status()

            file_path = info.json()["result"]["file_path"]

            content = await client.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}",
            )

            content.raise_for_status()

        mimetype = TelegramMediaClient._mimetype_from_path(file_path)

        return content.content, mimetype

    @staticmethod
    def _mimetype_from_path(file_path: str) -> str:

        lower = file_path.lower()

        if lower.endswith(".pdf"):

            return "application/pdf"

        if lower.endswith(".png"):

            return "image/png"

        if lower.endswith(".webp"):

            return "image/webp"

        return "image/jpeg"
