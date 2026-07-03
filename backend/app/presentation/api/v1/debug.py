from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.history.enriched_history_builder import (
    EnrichedHistoryBuilder,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)

router = APIRouter(
    prefix="/debug",
    tags=["Debug"],
)


@router.get("/activities")
async def enriched_activities():

    try:

        history = await LoadTrainingHistory.execute(limit=15)

        enriched = EnrichedHistoryBuilder.build(
            history
        )

        return [
            asdict(activity)
            for activity in enriched
        ]

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/memory/{profile}")
async def runner_memory(profile: str):

    try:

        return [
            asdict(entry)
            for entry in RunnerMemoryRepository().load(profile)
        ]

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )