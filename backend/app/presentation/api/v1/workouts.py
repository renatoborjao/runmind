from fastapi import APIRouter, Depends, HTTPException

from app.application.home.workouts_builder import WorkoutsBuilder
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/workouts", tags=["Workouts"])


@router.get("")
async def get_workouts(profile: str = Depends(current_profile)):
    """Treinos da semana (com detalhe) + prova-alvo do atleta logado — pra a aba
    de calendário/lista. Leituras baratas, sem IA."""

    try:

        return WorkoutsBuilder.build(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
