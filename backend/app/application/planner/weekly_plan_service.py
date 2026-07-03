from datetime import UTC, date, datetime

from app.application.planner.planner import TrainingPlanner
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

        reference_date = reference_date or datetime.now(UTC).date()

        current_week_start = WeeklyPlanService._week_start(
            reference_date,
        )

        repository = WeeklyPlanRepository()

        existing = repository.load(profile)

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
