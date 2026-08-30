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
        when: str = "eve",
    ) -> str | None:
        """Devolve a mensagem-proposta (e estagia a proposta) quando cabe:
        corpo em sobrecarga E há treino exigente. `when`:
        - "today" = treino exigente é HOJE (gatilho do despertar, dado fresco);
        - "eve" = treino exigente é AMANHÃ (véspera; on-demand)."""

        # treinador humano ou corpo sem sobrecarga: não mexe
        if runner.external_coach:

            return None

        if reading.body_state != BODY_STRAINED:

            return None

        if not plan.sessions or plan.source == "externo":

            return None

        done_days = WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

        if when == "today":

            # o treino exigente é HOJE (o seletor já garante data == hoje)
            session = BodyConductEngine.todays_demanding_session(
                plan, today, done_days
            )

        else:

            session = BodyConductEngine.next_demanding_session(
                plan, today, done_days
            )

            # só na VÉSPERA (exigente é AMANHÃ): antes disso um descanso ainda
            # pode restaurar o atleta — não se antecipa o corte.
            if session is not None and plan.session_date(
                session
            ) != today + timedelta(days=1):

                session = None

        if session is None:

            return None

        goal = BuildTrainingGoal.execute(runner)

        decision = await BodyConductEngine.decide(
            runner, plan, reading, session, today, goal.name, when=when,
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

        # a proposta DESCREVE o treino de hoje (o briefing pula o detalhe normal
        # quando ela entra) — então ela também leva a sugestão de tênis, senão o
        # atleta com armário fica sem o par nos dias de sobrecarga. Ver
        # [[ShoeRecommendationService]] e [[project_tracker_tenis]].
        return BodyConductProposer._with_shoe(
            profile, plan, session, decision.message
        )

    @staticmethod
    def _with_shoe(
        profile: str, plan: TrainingPlan, session, message: str
    ) -> str:
        """Anexa a sugestão de tênis do coach pra a sessão. Best-effort:
        silêncio total sem armário; falhar aqui nunca derruba a proposta."""

        try:

            from app.application.shoes.shoe_recommendation_service import (
                ShoeRecommendationService,
            )

            shoe = ShoeRecommendationService.line(
                profile,
                session,
                plan.session_date(session).isoformat(),
                sorted(plan.sessions, key=plan.session_date),
            )

            return f"{message}\n\n{shoe}" if shoe else message

        except Exception as e:

            print(f"Tênis na proposta de corpo de '{profile}' falhou: {e}")

            return message

    @staticmethod
    async def for_briefing(profile: str) -> str | None:
        """Ponto de entrada do 'bom dia' do despertar: carrega tudo e propõe o
        ajuste do treino de HOJE quando o corpo está em sobrecarga, com o dado
        FRESCO da noite. Best-effort — nunca derruba o briefing. Espelha
        ReadinessNotifier.block. Ver [[project_analise_corpo_garmin]]."""

        from app.application.coach.intelligence.body_reading_service import (
            BodyReadingService,
        )
        from app.application.planner.current_plan_provider import (
            CurrentPlanProvider,
        )
        from app.application.use_cases.load_training_history import (
            LoadTrainingHistory,
        )
        from app.core.clock import today_local

        try:

            reading, trajectory = BodyReadingService.read(
                profile, persist=False
            )

            # só sobrecarga real; barato quando não é (não carrega plano/histórico)
            if reading.body_state != BODY_STRAINED:

                return None

            runner, plan = await CurrentPlanProvider.for_profile(profile)

            history = await LoadTrainingHistory.execute(profile=profile)

            return await BodyConductProposer.propose(
                profile, runner, plan, reading, trajectory, history,
                today_local(), when="today",
            )

        except Exception as e:

            print(f"Proposta de corpo (briefing) de '{profile}' falhou: {e}")

            return None
