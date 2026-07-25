"""Aviso PROATIVO da véspera: quando amanhã tem um treino exigente e o corpo do
atleta pede freio HOJE (STRAINED), o coach manda uma PROPOSTA de aliviar/
remanejar — e o 'sim' aplica pelo ProposalFlow. Nunca muda o plano no silêncio,
nunca antecipa o corte (véspera, porque um descanso pode restaurar o atleta).

Roda de hora em hora; cada atleta é avaliado 1x/dia no horário local, no máximo
UMA proposta por treino exigente (dedup). Best-effort e silencioso quando o
corpo está bem, sem treino exigente amanhã, ou é treinador externo. Ver
[[project_analise_corpo_garmin]]."""

from datetime import timedelta

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.planning.body_conduct_engine import (
    BodyConductEngine,
)
from app.application.coach.planning.body_conduct_proposer import (
    BodyConductProposer,
)
from app.application.notifications.coach_outbox import CoachOutbox
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.domain.entities.body_reading import BODY_STRAINED
from app.infrastructure.persistence.dispatch_guard import DispatchGuard

# horário LOCAL do atleta em que o coach revisa o corpo na véspera (manhã: já
# reflete o sono/HRV da noite anterior, dá o dia pra ele decidir se descansa)
REVIEW_HOUR = 9


class BodyConductNotifier:

    @staticmethod
    async def notify_all() -> None:

        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        for profile in RunnerProfileRepository().list_all():

            try:

                await BodyConductNotifier._notify_one(profile)

            except Exception as e:

                print(f"Falha no aviso de corpo de '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # 1x/dia, no horário local; treinador externo fica de fora
        if local.hour != REVIEW_HOUR or runner.external_coach:

            return

        reading, trajectory = BodyReadingService.read(profile, persist=False)

        # só a SOBRECARGA real dispara (RECOVERY_FLAG se resolve na dose da
        # próxima geração, não cortando treino)
        if reading.body_state != BODY_STRAINED:

            return

        runner, plan = await CurrentPlanProvider.for_profile(profile)

        today = today_local()

        history = await LoadTrainingHistory.execute(profile=profile)

        done_days = WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

        session = BodyConductEngine.next_demanding_session(
            plan, today, done_days
        )

        # só na véspera de um treino exigente
        if session is None or plan.session_date(session) != today + timedelta(
            days=1
        ):

            return

        # uma proposta por treino exigente (não repropõe o mesmo dia)
        period = plan.session_date(session).isoformat()

        if DispatchGuard.already_sent("body_conduct", profile, period):

            return

        message = await BodyConductProposer.propose(
            profile, runner, plan, reading, trajectory, history, today,
        )

        if message is None:

            return

        await CoachOutbox.send(runner, message)

        DispatchGuard.mark("body_conduct", profile, period)
