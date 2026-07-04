import httpx

from app.core.config import get_settings


class TelegramService:

    @staticmethod
    async def send_message(
        chat_id: str,
        message: str,
    ):

        settings = get_settings()

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                f"https://api.telegram.org/bot"
                f"{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                },
            )

            print("==== TELEGRAM ====")
            print("STATUS:", response.status_code)
            print(response.text[:300])
            print("==================")

            response.raise_for_status()

            return response.json()
