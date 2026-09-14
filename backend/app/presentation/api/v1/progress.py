from fastapi import APIRouter, Depends, HTTPException

from app.application.home.evolution_builder import EvolutionBuilder
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get("")
async def get_progress(profile: str = Depends(current_profile)):
    """Evolução enriquecida: jornada, volume semanal, VO2max/projeções, FC rep."""

    try:

        return EvolutionBuilder.build(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
