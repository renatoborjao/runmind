from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.telegram.telegram_service import (
    TelegramService,
)
from app.infrastructure.notifications.whatsapp_service import (
    WhatsAppService,
)

TELEGRAM = "telegram"

WHATSAPP = "whatsapp"


class NotificationService:
    """Envio multicanal: escolhe WhatsApp ou Telegram pelo canal do
    atleta. A resposta sempre volta pelo canal de origem."""

    @staticmethod
    async def send(
        runner: RunnerProfile,
        message: str,
    ) -> None:
        """Proativo/reativo com perfil: usa o canal gravado no atleta."""

        await NotificationService.send_to(
            channel=runner.channel,
            address=(
                runner.telegram_id
                if runner.channel == TELEGRAM
                else runner.phone
            ),
            message=message,
        )

    @staticmethod
    async def send_to(
        channel: str,
        address: str,
        message: str,
    ) -> None:
        """Resposta a uma mensagem de entrada quando ainda não há
        perfil (onboarding) — endereço bruto do canal."""

        if channel == TELEGRAM:

            await TelegramService.send_message(
                chat_id=address,
                message=message,
            )

            return

        await WhatsAppService.send_message(
            phone=address,
            message=message,
        )

    # Retrocompat: WhatsApp direto por telefone (usos legados/testes).
    @staticmethod
    async def send_training_feedback(
        phone: str,
        message: str,
    ) -> None:

        await WhatsAppService.send_message(
            phone=phone,
            message=message,
        )
