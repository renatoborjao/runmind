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
    ) -> str:

        reply = await OnboardingFlow.handle(
            channel=channel,
            address=address,
            incoming_text=incoming_text,
            sender_name=sender_name,
            media=media,
        )

        await NotificationService.send_to(
            channel=channel,
            address=address,
            message=reply,
        )

        return reply
