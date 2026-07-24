from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.history.enriched_history_builder import (
    EnrichedHistoryBuilder,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
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


@router.get("/learnings/{profile}")
async def coach_learnings(profile: str):
    """O que o cérebro coach aprendeu observando o atleta — janela de
    inspeção do modo observação (antes de ligar a injeção no prompt)."""

    try:

        return [
            asdict(entry)
            for entry in CoachLearningRepository().load(profile)
        ]

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )