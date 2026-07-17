"""Recap mensal — no dia 1 de cada mês, manda o balanço do mês que fechou
(km, treinos, consistência, recordes) pensado pra ser ENCAMINHADO. Espelha o
WeeklyReviewNotifier: roda de hora em hora, cada _notify_one decide se é a
hora certa (LOCAL) do atleta, com dedup por mês."""

from datetime import date

from app.application.notifications.coach_outbox import CoachOutbox
from app.application.review.monthly_recap_builder import MonthlyRecapBuilder
from app.application.review.monthly_recap_message_formatter import (
    MonthlyRecapMessageFormatter,
)
from app.application.review.monthly_recap_narrative_writer import (
    MonthlyRecapNarrativeWriter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_in, use_athlete_timezone
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# cobre um mês cheio de treinos com folga
HISTORY_LIMIT = 90

# dia 1 do mês, 9h LOCAL: recapitula o mês que acabou de fechar
RECAP_DAY = 1

RECAP_HOUR = 9


def _previous_month_start(local_date: date) -> date:

    if local_date.month == 1:

        return date(local_date.year - 1, 12, 1)

    return date(local_date.year, local_date.month - 1, 1)


def _month_key(month_start: date) -> str:

    return f"{month_start.year}-{month_start.month:02d}"


class MonthlyRecapNotifier:

    @staticmethod
    async def notify_all() -> None:
        """Roda de HORA EM HORA; cada _notify_one decide se é o horário
        local do atleta (dia 1, 9h) e faz dedup."""

        for profile in RunnerProfileRepository().list_all():

            try:

                await MonthlyRecapNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha ao enviar recap mensal para '{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        if local.day != RECAP_DAY or local.hour != RECAP_HOUR:

            return

        month_start = _previous_month_start(local.date())

        period = _month_key(month_start)

        if DispatchGuard.already_sent("monthly_recap", profile, period):

            return

        DispatchGuard.mark("monthly_recap", profile, period)

        history = await LoadTrainingHistory.execute(
            profile=profile,
            limit=HISTORY_LIMIT,
        )

        recap = MonthlyRecapBuilder.build(
            runner,
            history,
            month_start,
        )

        if recap is None:

            return

        narrative = await MonthlyRecapNarrativeWriter.write(
            runner.name,
            recap,
        )

        message = MonthlyRecapMessageFormatter.format(
            runner.name,
            recap,
            narrative,
        )

        await CoachOutbox.send(
            runner,
            message,
        )
