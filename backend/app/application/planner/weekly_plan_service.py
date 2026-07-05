from datetime import date, timedelta

from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.application.planner.engines.progression_engine import (
    ProgressionEngine,
)
from app.application.planner.planner import TrainingPlanner
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.clock import today_local
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WeeklyPlanService:

    @staticmethod
    def get_or_generate(
        profile: str,
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        metrics: RunnerMetrics,
        goal: TrainingGoal,
        reference_date: date | None = None,
        force: bool = False,
        history: TrainingHistory | None = None,
    ) -> TrainingPlan:

        reference_date = reference_date or today_local()

        current_week_start = WeeklyPlanService._week_start(
            reference_date,
        )

        repository = WeeklyPlanRepository()

        existing = repository.load(profile)

        # Atleta com treinador humano: NUNCA gera plano. Acompanha o
        # último plano enviado (mesmo de semana anterior) ou um plano
        # vazio até o corredor mandar o print da semana.
        if runner.external_coach:

            if existing is not None:

                return existing

            return TrainingPlan(
                athlete_name=runner.name,
                objective=runner.goal,
                phase="EXTERNO",
                weekly_volume=0,
                running_days=[],
                week_start=current_week_start,
                sessions=[],
                source="externo",
            )

        if (
            not force
            and existing is not None
            and existing.week_start == current_week_start
        ):

            return existing

        training_week = WeeklyPlanService._training_week(
            repository,
            profile,
            current_week_start,
        )

        baseline, target_volume = WeeklyPlanService._progression(
            profile,
            runner,
            assessment,
            goal,
            history,
            repository,
            current_week_start,
        )

        new_plan = TrainingPlanner.generate(
            runner,
            assessment,
            goal,
            metrics,
            current_week_start,
            training_week,
            baseline=baseline,
            target_volume=target_volume,
        )

        repository.save(profile, new_plan)

        return new_plan

    @staticmethod
    def _progression(
        profile: str,
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        goal: TrainingGoal,
        history: TrainingHistory | None,
        repository: WeeklyPlanRepository,
        current_week_start: date,
    ):
        """Volume-alvo da semana (Track A): parte do retrato real e progride
        pela consistência + execução da semana anterior. Sem histórico
        passado (ou sem base utilizável), volta ao caminho antigo (None)."""

        if history is None:

            return None, None

        baseline = RunnerBaselineBuilder.build(history, runner)

        if baseline.weekly_km <= 0:

            return None, None

        recent_adherence = WeeklyPlanService._recent_adherence(
            profile,
            repository,
            history,
            current_week_start,
        )

        target = ProgressionEngine.next_weekly_volume(
            baseline=baseline,
            consistency=assessment.consistency,
            recent_adherence=recent_adherence,
            has_race=goal.race_date is not None,
        )

        return baseline, target

    # nº de semanas anteriores olhadas pra decidir regressão (2+ = regride)
    ADHERENCE_LOOKBACK_WEEKS = 2

    @staticmethod
    def _recent_adherence(
        profile: str,
        repository: WeeklyPlanRepository,
        history: TrainingHistory,
        current_week_start: date,
    ) -> list[float]:
        """Fração das sessões cumpridas em cada uma das últimas semanas que
        tiveram plano (cronológico, a mais recente por último). Uma semana
        atípica isolada não derruba o plano — só 2+ seguidas."""

        by_week = {
            plan.week_start: plan
            for plan in repository.history(profile)
        }

        recent = []

        for weeks_ago in range(
            WeeklyPlanService.ADHERENCE_LOOKBACK_WEEKS, 0, -1
        ):

            week_start = current_week_start - timedelta(days=7 * weeks_ago)

            plan = by_week.get(week_start)

            if plan is None or not plan.sessions:

                continue

            done = WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )

            recent.append(len(done) / len(plan.sessions))

        return recent

    @staticmethod
    def _training_week(
        repository: WeeklyPlanRepository,
        profile: str,
        current_week_start: date,
    ) -> int:
        """Índice da semana de treino no RunMind: nº de semanas já
        planejadas antes desta + 1. Determinístico (vem do histórico),
        idempotente na regeração da mesma semana."""

        past_weeks = {
            plan.week_start
            for plan in repository.history(profile)
            if plan.week_start < current_week_start
        }

        return len(past_weeks) + 1

    @staticmethod
    def _week_start(
        reference_date: date,
    ) -> date:
        """Segunda-feira da semana que o plano cobre.

        Domingo é véspera: planejamos a semana que COMEÇA na segunda
        seguinte, para o plano nunca nascer com datas passadas (o
        notificador roda domingo 15h). Segunda a sábado usam a segunda
        da própria semana corrente."""

        # weekday(): segunda=0 ... domingo=6
        if reference_date.weekday() == 6:

            return reference_date + timedelta(days=1)

        return reference_date - timedelta(
            days=reference_date.weekday(),
        )
