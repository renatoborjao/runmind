from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.coach.conversation.rpe_flow import RpeFlow
from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.checkin_service import (
    CheckinService,
)
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.coach.intelligence.state_portrait_service import (
    StatePortraitService,
)
from app.application.coach.writer.state_portrait_writer import (
    StatePortraitWriter,
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
from app.infrastructure.persistence.checkin_repository import (
    CheckinRepository,
)
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
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
    """Veredito de evolução (EF curto+longo + VO₂máx + FC-repouso). Janela de
    inspeção pra conferir a leitura contra a realidade — mostra cada sinal e
    quais ainda estão sem lastro."""

    try:

        return asdict(FitnessReadingService.read_evolution(profile))

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/portrait/{profile}")
async def portrait(profile: str):
    """Retrato ÚNICO "como você está": corpo & carga + forma cruzados. Mostra o
    veredito de cada eixo e a mensagem composta — janela de inspeção do
    panorama sem enviar nada ao atleta."""

    try:

        reading, evolution = StatePortraitService.read(profile, persist=False)

        return {
            "body_state": reading.body_state,
            "limiter": reading.limiter,
            "load_status": reading.load.status,
            "evolution_direction": evolution.direction,
            "evolution_stale": evolution.stale,
            "days_since_last_run": evolution.days_since_last_run,
            "message": StatePortraitWriter.write(
                reading, evolution, profile
            ),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/session-rpe/{profile}")
async def session_rpe(profile: str):
    """sRPE por sessão (esforço percebido → carga subjetiva) + o pendente e a
    nota de dose que entra no plano."""

    try:

        repo = SessionRpeRepository()

        return {
            "pending": repo.get_pending(profile),
            "dose_note": RpeFlow.recent_note(profile),
            "sessions": [asdict(s) for s in repo.load_sessions(profile)],
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/checkins/{profile}")
async def checkins(profile: str):
    """Check-ins de sensação (estado subjetivo relatado) + o estado recente que
    entra na dose. Janela de inspeção da captura reativa."""

    try:

        return {
            "recent_rendered": CheckinService.render_recent(profile),
            "checkins": [asdict(c) for c in CheckinRepository().load(profile)],
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )