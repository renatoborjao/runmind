from datetime import date, timedelta

from app.application.planner.planner import TrainingPlanner
from app.core.clock import today_local
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
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

        new_plan = TrainingPlanner.generate(
            runner,
            assessment,
            goal,
            metrics,
            current_week_start,
            training_week,
        )

        repository.save(profile, new_plan)

        return new_plan

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
