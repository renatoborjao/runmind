import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import get_settings

router = APIRouter(
    prefix="/telegram",
    tags=["Telegram"],
)


@router.post("/register-webhook")
async def register_webhook():
    """Registra o webhook do bot no Telegram (setWebhook) apontando
    para a URL pública do RunMind, com o secret de segurança."""

    settings = get_settings()

    if not settings.telegram_bot_token:

        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN não configurado no .env",
        )

    webhook_url = (
        f"{settings.public_base_url}/api/v1/webhooks/telegram"
    )

    async with httpx.AsyncClient(timeout=15) as client:

        response = await client.post(
            f"https://api.telegram.org/bot"
            f"{settings.telegram_bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": settings.telegram_webhook_secret,
                "allowed_updates": ["message"],
            },
        )

    response.raise_for_status()

    return {
        "webhook_url": webhook_url,
        "telegram_response": response.json(),
    }


@router.get("/me")
async def me():

    settings = get_settings()

    async with httpx.AsyncClient(timeout=10) as client:

        response = await client.get(
            f"https://api.telegram.org/bot"
            f"{settings.telegram_bot_token}/getMe",
        )

    response.raise_for_status()

    return response.json()
