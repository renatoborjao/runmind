from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class DailyTrainingNotifier:
    """Lembrete matinal (06h): no dia em que há treino, manda a sessão
    detalhada. Dia de descanso não gera mensagem."""

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await DailyTrainingNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha no lembrete matinal para '{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner, plan = await CurrentPlanProvider.for_profile(profile)

        message = WeeklyPlanMessageFormatter.today_session_message(
            runner.name,
            plan,
        )

        # Dia de descanso: nada a enviar.
        if message is None:

            return

        await NotificationService.send(
            runner,
            message,
        )
