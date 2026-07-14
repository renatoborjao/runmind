"""Envia uma mensagem AUTOMÁTICA do coach (análise pós-treino, briefing, plano
da semana, review) E a registra no outbox — pra o coach lembrar do que disse
quando o atleta comentar depois no chat. O chat normal já grava seus próprios
turnos (user/assistant); este outbox é só pras mensagens de FORA do fluxo de
conversa, que não entrariam no histórico."""

from app.application.notifications.notification_service import (
    NotificationService,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)
from app.infrastructure.persistence.coach_outbox_repository import (
    CoachOutboxRepository,
)


class CoachOutbox:

    @staticmethod
    async def send(runner: RunnerProfile, message: str) -> None:

        await NotificationService.send(runner, message)

        # registrar no outbox NUNCA pode derrubar o envio já feito
        try:

            CoachOutboxRepository().append(
                runner.id,
                to_plain_text(message),
            )

        except Exception as e:

            print(
                f"Falha ao registrar mensagem do coach ({runner.id}): {e}"
            )
