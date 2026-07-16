from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.onboarding.onboarding_flow import OnboardingFlow


class OnboardingEvent:
    """Mensagem de número desconhecido: conduz o cadastro do corredor."""

    @staticmethod
    async def execute(
        channel: str,
        address: str,
        incoming_text: str,
        sender_name: str = "",
        media: dict | None = None,
        send_fallback: bool = True,
    ) -> str:

        # send_fallback=False (tentativa não-final do retry adiado): se o
        # Gemini estiver fora, handle levanta AssistantUnavailable ANTES de
        # enviar/gravar — o webhook tenta de novo em vez de mandar o fallback.
        reply = await OnboardingFlow.handle(
            channel=channel,
            address=address,
            incoming_text=incoming_text,
            sender_name=sender_name,
            media=media,
            send_fallback=send_fallback,
        )

        await NotificationService.send_to(
            channel=channel,
            address=address,
            message=reply,
        )

        return reply
