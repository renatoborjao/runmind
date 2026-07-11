from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.application.planner.missed_workout_flow import MissedWorkoutFlow
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class MorningBriefingNotifier:
    """Briefing matinal (06h) numa mensagem só, por atleta: primeiro o furo de
    ONTEM (se houve — o coach só avisa ou propõe re-plano), depois o lembrete
    do treino de HOJE. Um envio só, na ordem certa. Falha de um atleta não
    derruba os outros."""

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await MorningBriefingNotifier._notify_one(profile)

            except Exception as e:

                print(f"Briefing matinal falhou para '{profile}': {e}")

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        parts: list[str] = []

        runner = None

        # Furo de ONTEM primeiro (pode guardar uma proposta pro 'sim').
        missed = await MissedWorkoutFlow.process(profile)

        if missed is not None:

            runner, missed_message = missed

            parts.append(missed_message)

        # Depois o treino de HOJE (dia de descanso volta None).
        today = await DailyTrainingNotifier.build(profile)

        if today is not None:

            runner, today_message = today

            parts.append(today_message)

        # Nada a dizer (sem furo e hoje é descanso): silêncio.
        if not parts:

            return

        await NotificationService.send(
            runner,
            "\n\n".join(parts),
        )
