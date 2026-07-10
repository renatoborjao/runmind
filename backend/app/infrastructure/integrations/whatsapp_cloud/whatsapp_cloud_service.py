import httpx

from app.core.config import get_settings
from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)


class WhatsAppCloudService:
    """Envio pela Cloud API oficial da Meta (Graph API). Substitui a
    Evolution sem mudar a lógica do coach — a interface é a mesma
    (send_message(phone, message)).

    ATENÇÃO à janela de 24h: mensagem de texto livre só é entregue se o
    atleta falou com o bot nas últimas 24h. Fora disso a Meta EXIGE um
    template aprovado (send_template) — é o caso do lembrete das 06h e do
    plano de domingo, que partem do bot. Feedback logo após o treino
    costuma cair na janela se o atleta conversou; senão, vira template."""

    @staticmethod
    def _base_url() -> str:

        settings = get_settings()

        return (
            f"https://graph.facebook.com/"
            f"{settings.whatsapp_graph_version}/"
            f"{settings.whatsapp_phone_number_id}/messages"
        )

    @staticmethod
    def _headers() -> dict:

        settings = get_settings()

        return {
            "Authorization": f"Bearer {settings.whatsapp_cloud_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    async def send_message(
        phone: str,
        message: str,
    ):
        """Texto livre (só dentro da janela de 24h). O markdown do Gemini
        é normalizado como no Telegram (WhatsApp não renderiza '**')."""

        message = to_plain_text(message)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message,
            },
        }

        return await WhatsAppCloudService._post(payload, phone)

    @staticmethod
    async def send_template(
        phone: str,
        template_name: str,
        language: str = "pt_BR",
        body_params: list[str] | None = None,
    ):
        """Mensagem iniciada pelo bot FORA da janela de 24h (lembrete,
        plano, feedback quando o atleta não conversou). Exige template
        previamente aprovado na Meta. body_params preenche as {{1}},{{2}}
        do corpo, na ordem."""

        components = []

        if body_params:

            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(p)}
                        for p in body_params
                    ],
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }

        return await WhatsAppCloudService._post(payload, phone)

    @staticmethod
    async def _post(
        payload: dict,
        phone: str,
    ):

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                WhatsAppCloudService._base_url(),
                headers=WhatsAppCloudService._headers(),
                json=payload,
            )

            print("==== WHATSAPP CLOUD ====")
            print("STATUS:", response.status_code)
            print(response.text[:300])
            print("========================")

            response.raise_for_status()

            return response.json()
