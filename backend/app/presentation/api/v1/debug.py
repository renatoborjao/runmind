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
from app.application.coach.intelligence.readiness_service import (
    ReadinessService,
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


@router.get("/brain/{profile}")
async def coach_brain_log(profile: str, limit: int = 40):
    """Decisões recentes do cérebro do coach (modo observação): o que ele
    decidiu por mensagem — ação/escopo/dia/cartão/pendência + trecho da fala,
    e quando caiu no fallback. Pra acompanhar semana a semana e pegar deriva
    antes de virar print ruim. Mais recentes primeiro."""

    try:

        from app.infrastructure.persistence.coach_brain_health_repository import (
            CoachBrainHealthRepository,
        )
        from app.infrastructure.persistence.coach_brain_log_repository import (
            CoachBrainLogRepository,
        )

        entries = CoachBrainLogRepository().load(profile)

        # saúde GLOBAL do cérebro (taxa de fallback na janela rolante) — o sinal
        # que o vigia usa pra alertar; exposto aqui pra inspeção manual também
        health = CoachBrainHealthRepository().load()

        window = health.get("window", [])

        fallback_rate = round(sum(window) / len(window), 3) if window else 0.0

        return {
            "health": {
                "fallback_rate": fallback_rate,
                "sample": len(window),
                "alerted": bool(health.get("alerted", False)),
            },
            "recent": list(reversed(entries[-limit:])),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/proactive/{profile}")
async def proactive_ledger(profile: str, limit: int = 20):
    """Diário do GOVERNADOR de proativos: o que o coach INICIOU (tipo/tier/dia/
    hora) — a visão unificada que faltava pra pegar proativo repetido/fora de
    hora/empilhado ANTES de o atleta ver. Mostra as entradas recentes, as de
    HOJE e quanto do teto diário de EXTRAS já foi usado. Mais recentes primeiro."""

    try:

        from app.application.notifications.proactive_governor import HIGH
        from app.core.clock import today_local
        from app.core.config import get_settings
        from app.infrastructure.persistence.proactive_ledger_repository import (
            ProactiveLedgerRepository,
        )

        settings = get_settings()

        ledger = ProactiveLedgerRepository()

        day = today_local().isoformat()

        today = ledger.today(profile, day)

        extras_used = sum(1 for e in today if e.get("tier", HIGH) < HIGH)

        return {
            "governor_active": settings.proactive_governor_active_for(profile),
            "daily_budget": settings.proactive_daily_budget,
            "today": {
                "day": day,
                "sent": [e.get("kind") for e in today],
                "extras_used": extras_used,
                "extras_left": max(
                    0, settings.proactive_daily_budget - extras_used
                ),
            },
            "recent": list(reversed(ledger.recent(profile, limit))),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/proactive-preview/{profile}")
async def proactive_preview(profile: str):
    """DRY-RUN (não envia): a sequência de toques de PROVA que ainda vai sair —
    data, marco, se já saiu e o CONTEÚDO real. É o preview que pega bug de
    timing (polimento fora de hora, marco pulado) ANTES do atleta ver. Vazio
    quando não há prova por vir."""

    try:

        from app.application.review.race_companion_notifier import (
            RaceCompanionNotifier,
        )

        return {"race_schedule": await RaceCompanionNotifier.preview(profile)}

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


@router.get("/pace-zones/{profile}")
async def pace_zones(profile: str):
    """Zonas de pace Z1–Z5 derivadas do ritmo real do atleta + o cartão
    formatado. Janela de inspeção pra conferir as faixas antes de responder."""

    from app.application.coach.writer.pace_zones_writer import PaceZonesWriter
    from app.application.history.pace_model_builder import PaceModelBuilder
    from app.application.history.pace_zone_builder import PaceZoneBuilder
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )
    from app.domain.entities.pace_model import (
        SOURCE_DECLARED,
        SOURCE_ROOKIE,
    )
    from app.infrastructure.persistence.runner_profile_repository import (
        RunnerProfileRepository,
    )

    try:

        runner = RunnerProfileRepository().load(profile)

        if runner is None:

            raise HTTPException(status_code=404, detail="perfil não encontrado")

        history = await LoadTrainingHistory.execute(profile=profile)

        model = PaceModelBuilder.build(history, runner)

        zones = PaceZoneBuilder.build(model)

        estimated = model.source in (SOURCE_DECLARED, SOURCE_ROOKIE)

        return {
            "model": asdict(model),
            "zones": [asdict(zone) for zone in zones.zones],
            "card": PaceZonesWriter.write(
                zones, runner.name, estimated=estimated
            ),
        }

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/sleep/{profile}")
async def sleep(profile: str):
    """Sono como eixo próprio (média/tendência/regularidade/dívida) + o cartão.
    Janela de inspeção pra conferir a leitura antes de responder."""

    from app.application.coach.intelligence.sleep_reading_service import (
        SleepReadingService,
    )
    from app.application.coach.writer.sleep_reading_writer import (
        SleepReadingWriter,
    )
    from app.application.history.sleep_performance_analyzer import (
        SleepPerformanceAnalyzer,
    )
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )
    from app.infrastructure.persistence.garmin_health_repository import (
        GarminHealthRepository,
    )

    try:

        reading = SleepReadingService.read(profile)

        history = await LoadTrainingHistory.execute(profile=profile)

        impact = SleepPerformanceAnalyzer.analyze(
            history.activities, GarminHealthRepository().load(profile)
        )

        return {
            "reading": asdict(reading),
            "impact": asdict(impact),
            "card": SleepReadingWriter.write(reading, profile, impact=impact),
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


@router.get("/readiness/{profile}")
async def readiness(profile: str):
    """Vigia de prontidão (MODO OBSERVAÇÃO): avalia o corpo à luz do treino de
    hoje, mostra o veredito e o diário do que o coach DIRIA. Nada é enviado —
    é a janela pra conferir os alertas antes de ligar o envio real."""

    from app.infrastructure.persistence.readiness_diary_repository import (
        ReadinessDiaryRepository,
    )

    try:

        verdict, entry = await ReadinessService.evaluate(profile, persist=True)

        return {
            "verdict": asdict(verdict),
            "today": asdict(entry),
            "diary": [
                asdict(e) for e in ReadinessDiaryRepository().load(profile)
            ],
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )