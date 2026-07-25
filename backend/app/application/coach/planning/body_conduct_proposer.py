"""Decide e ESTAGIA a proposta de conduta quando, na véspera de um treino
exigente, o corpo pede freio. Compartilhado pelos dois canais: o aviso proativo
da véspera (BodyConductNotifier) e a pergunta 'como tá meu corpo?' (on-demand).

Nunca aplica nada: guarda a proposta (PlanProposalRepository) e devolve a
mensagem. O 'sim' do atleta resolve pelo ProposalFlow (que já reconcilia o
Garmin e grava o sinal Fonte A pro cérebro). Coach lidera pelos dados; atleta
confirma pelo que sente na véspera."""

from datetime import date, timedelta

from app.application.coach.planning.body_conduct_engine import (
    BodyConductEngine,
)
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.core.clock import now_local
from app.domain.entities.body_reading import BODY_STRAINED, BodyReading
from app.domain.entities.body_reading_snapshot import BodyTrajectory
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)


class BodyConductProposer:

    @staticmethod
    async def propose(
        profile: str,
        runner: RunnerProfile,
        plan: TrainingPlan,
        reading: BodyReading,
        trajectory: BodyTrajectory | None,
        history: TrainingHistory,
        today: date,
    ) -> str | None:
        """Devolve a mensagem-proposta (e estagia a proposta) quando cabe:
        corpo em sobrecarga E há treino exigente AMANHÃ. Senão, None."""

        # treinador humano ou corpo sem sobrecarga: não mexe
        if runner.external_coach:

            return None

        if reading.body_state != BODY_STRAINED:

            return None

        if not plan.sessions or plan.source == "externo":

            return None

        done_days = WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

        session = BodyConductEngine.next_demanding_session(
            plan, today, done_days
        )

        # só na VÉSPERA (treino exigente é AMANHÃ). Antes disso, um descanso
        # ainda pode restaurar o atleta — não se antecipa o corte.
        if session is None or plan.session_date(session) != today + timedelta(
            days=1
        ):

            return None

        goal = BuildTrainingGoal.execute(runner)

        decision = await BodyConductEngine.decide(
            runner, plan, reading, session, today, goal.name,
        )

        # IA caiu ou o coach decidiu MANTER: sem proposta
        if decision is None or decision.action == "keep":

            return None

        PlanProposalRepository().save(
            profile,
            PlanProposal(
                kind=f"body_{decision.action}",
                week_start=plan.week_start.isoformat(),
                preview=decision.message,
                created_at=now_local().isoformat(),
                operations=decision.operations,
            ),
        )

        return decision.message
