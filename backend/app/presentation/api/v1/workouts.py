from fastapi import APIRouter, Depends, HTTPException

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

        return data

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
