import httpx

from app.core.config import get_settings


class WhatsAppService:

    @staticmethod
    async def send_message(
        phone: str,
        message: str,
    ):

        settings = get_settings()

        # canal desligado (Evolution fora do ar): loga alto e não tenta —
        # melhor um aviso claro no console que um traceback por envio
        if not settings.whatsapp_enabled:

            print(
                f"WhatsApp DESLIGADO (WHATSAPP_ENABLED=false) — "
                f"mensagem para {phone} NÃO enviada."
            )

            return None

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