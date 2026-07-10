import httpx

from app.core.config import get_settings
from app.infrastructure.integrations.whatsapp_cloud.whatsapp_cloud_service import (
    WhatsAppCloudService,
)


class WhatsAppService:
    """Porta única de envio por WhatsApp. Despacha para o driver
    configurado (WHATSAPP_PROVIDER): "cloud" (Cloud API oficial) ou
    "evolution" (não-oficial). NotificationService fala só com esta
    classe — a troca de provider não vaza pra cima."""

    @staticmethod
    async def send_message(
        phone: str,
        message: str,
    ):

        settings = get_settings()

        # canal desligado (driver fora do ar): loga alto e não tenta —
        # melhor um aviso claro no console que um traceback por envio
        if not settings.whatsapp_enabled:

            print(
                f"WhatsApp DESLIGADO (WHATSAPP_ENABLED=false) — "
                f"mensagem para {phone} NÃO enviada."
            )

            return None

        if settings.whatsapp_provider == "cloud":

            return await WhatsAppCloudService.send_message(
                phone=phone,
                message=message,
            )

        return await WhatsAppService._send_evolution(phone, message)

    @staticmethod
    async def _send_evolution(
        phone: str,
        message: str,
    ):

        settings = get_settings()

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                f"{settings.evolution_api_url}/message/sendText/{settings.evolution_instance}",
                headers={
                    "apikey": settings.evolution_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "number": phone,
                    "text": message,
                },
            )

            print("====================================")
            print("STATUS:", response.status_code)
            print(response.text)
            print("====================================")

            response.raise_for_status()

            return response.json()
