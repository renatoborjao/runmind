from fastapi import APIRouter, Depends, HTTPException

from app.application.home.home_summary_builder import HomeSummaryBuilder
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("")
async def get_home(profile: str = Depends(current_profile)):
    """Resumo da home do atleta LOGADO (prontidão, treino de hoje, semana,
    evolução, tênis). Leituras baratas — sem IA, sem gerar plano."""

    try:

        return HomeSummaryBuilder.build(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
