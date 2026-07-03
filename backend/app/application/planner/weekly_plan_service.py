from datetime import date

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
            existing is not None
            and existing.week_start == current_week_start
        ):

            return existing

        new_plan = TrainingPlanner.generate(
            runner,
            assessment,
            goal,
            metrics,
            current_week_start,
        )

        repository.save(profile, new_plan)

        return new_plan

    @staticmethod
    def _week_start(
        reference_date: date,
    ) -> date:

        iso_year, iso_week, _ = reference_date.isocalendar()

        return date.fromisocalendar(iso_year, iso_week, 1)
