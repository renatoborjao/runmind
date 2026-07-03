from app.infrastructure.notifications.whatsapp_service import (
    WhatsAppService,
)


class NotificationService:

    @staticmethod
    async def send_training_feedback(
        phone: str,
        message: str,
    ):

        await WhatsAppService.send_message(
            phone=phone,
            message=message,
        )