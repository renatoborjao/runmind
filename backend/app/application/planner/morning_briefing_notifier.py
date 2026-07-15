from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.application.planner.missed_workout_flow import MissedWorkoutFlow
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# hora LOCAL do atleta em que o briefing sai
BRIEFING_HOUR = 6


class MorningBriefingNotifier:
    """Briefing matinal (06h) numa mensagem só, por atleta: primeiro o furo de
    ONTEM (se houve — o coach só avisa ou propõe re-plano), depois o lembrete
    do treino de HOJE. Um envio só, na ordem certa. Falha de um atleta não
    derruba os outros."""

    @staticmethod
    async def notify_all() -> None:
        """Roda de HORA EM HORA; cada _notify_one decide se é 06h no fuso do
        atleta e faz dedup (uma vez por dia)."""

        for profile in RunnerProfileRepository().list_all():

            try:

                await MorningBriefingNotifier._notify_one(profile)

            except Exception as e:

                print(f"Briefing matinal falhou para '{profile}': {e}")

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner = LoadRunnerProfile.execute(profile)

        # fuso do atleta primeiro: ontem/hoje/semana no horário dele
        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # só quando é 06h LOCAL do atleta, uma vez por dia (dedup)
        if local.hour != BRIEFING_HOUR:

            return

        period = local.date().isoformat()

        if DispatchGuard.already_sent("briefing", profile, period):

            return

        DispatchGuard.mark("briefing", profile, period)

        parts: list[str] = []

        # Furo de ONTEM primeiro (pode guardar uma proposta pro 'sim').
        missed = await MissedWorkoutFlow.process(profile)

        if missed is not None:

            _, missed_message = missed

            parts.append(missed_message)

        # Depois o treino de HOJE (dia de descanso volta None).
        today = await DailyTrainingNotifier.build(profile)

        if today is not None:

            _, today_message = today

            parts.append(today_message)

        # Nada a dizer (sem furo e hoje é descanso): silêncio.
        if not parts:

            return

        await CoachOutbox.send(
            runner,
            "\n\n".join(parts),
        )
