from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.application.garmin.watch_day import watch_day_closed
from app.application.home.week_plan_builder import WeekPlanBuilder
from app.application.home.workouts_builder import WorkoutsBuilder
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/workouts", tags=["Workouts"])


@router.get("")
async def get_workouts(profile: str = Depends(current_profile)):
    """Treinos da semana (com detalhe) + prova-alvo do atleta logado — pra a aba
    de calendário/lista. Leituras baratas, sem IA.

    `garmin_connected` habilita/desconde a ação 'Enviar pro relógio' no app: só
    faz sentido pra quem tem Garmin conectado (o push agenda em Treino →
    Programados). Check local e barato (existência do token)."""

    try:

        data = WorkoutsBuilder.build(profile)

        data["garmin_connected"] = GarminClient.is_connected(profile)

        # janela da noite: treino movido pra HOJE não desce mais pro relógio —
        # o app avisa ANTES do 'tem certeza?' (ver watch_day)
        data["watch_day_closed"] = watch_day_closed()

        return data

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/week")
async def get_week_plan(
    week_start: str | None = None,
    profile: str = Depends(current_profile),
):
    """O PLANO DA SEMANA (o do chat com o coach, navegável): objetivo, bloco, fase,
    treino a treino com passos, o que já foi feito ao lado de cada dia e os totais
    da semana. `week_start` (segunda, AAAA-MM-DD) abre uma semana ANTERIOR do
    histórico; sem ele, a semana do plano atual. Só leitura, sem IA."""

    if week_start is not None:

        try:

            date.fromisoformat(week_start)

        except ValueError:

            raise HTTPException(status_code=422, detail="Semana inválida (use AAAA-MM-DD).")

    try:

        return WeekPlanBuilder.build(profile, week_start)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
