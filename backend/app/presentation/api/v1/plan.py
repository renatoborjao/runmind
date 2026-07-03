from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.runner_metrics import RunnerMetricsBuilder
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.domain.entities.training_goal import TrainingGoal
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

router = APIRouter(
    prefix="/plan",
    tags=["Plan"],
)


@router.get("")
async def get_plan():

    try:

        profile = "runner_profile"

        runner = RunnerProfileRepository().load(profile)

        history = await LoadTrainingHistory.execute()

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = RunnerMetricsBuilder.build(
            history,
        )

        goal = TrainingGoal(
            name=runner.goal,
            distance_km=10,
            target_time=runner.target_time,
            race_date=None,
        )

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
        )

        return {
            "runner": asdict(runner),
            "assessment": asdict(assessment),
            "plan": asdict(plan),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )