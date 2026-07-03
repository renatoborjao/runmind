from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.application.use_cases.build_training_goal import BuildTrainingGoal

router = APIRouter(
    prefix="/plan",
    tags=["Plan"],
)


@router.get("")
async def get_plan(profile: str = "renato"):

    try:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

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