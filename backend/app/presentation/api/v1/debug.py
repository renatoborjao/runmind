from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.history.enriched_history_builder import (
    EnrichedHistoryBuilder,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
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


@router.get("/body-trajectory/{profile}")
async def body_trajectory(profile: str):
    """Histórico de leituras do corpo + a trajetória atual (foto -> filme).
    Janela de inspeção do modo observação: é aqui que se confere se a
    trajetória bate com a realidade antes de ligar a frase na mensagem."""

    try:

        snapshots = [
            asdict(s)
            for s in BodyReadingHistoryRepository().load(profile)
        ]

        # leitura de hoje SEM gravar (só inspeção)
        reading, trajectory = BodyReadingService.read(profile, persist=False)

        return {
            "current_state": reading.body_state,
            "trajectory": asdict(trajectory),
            "snapshots": snapshots,
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/fitness/{profile}")
async def fitness(profile: str):
    """Tendência de eficiência aeróbica (o eixo 'estou evoluindo?'). Janela de
    inspeção pra conferir a leitura contra a realidade antes/depois de ligar."""

    try:

        return asdict(FitnessReadingService.read(profile))

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )