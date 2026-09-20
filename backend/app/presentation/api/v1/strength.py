from fastapi import APIRouter, Depends

from app.application.strength.strength_library import library
from app.application.strength.strength_routine_builder import (
    StrengthRoutineBuilder,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/strength", tags=["Strength"])


@router.get("/library")
async def strength_library():
    """Biblioteca de exercícios de fortalecimento para quem corre (conteúdo
    curado, estático, sem PII) — aberta, pra o app montar a tela e o coach
    montar rotinas a partir dela."""

    return library()


@router.get("/routine")
async def strength_routine(profile: str = Depends(current_profile)):
    """A rotina de força que o COACH montou pra ESTE atleta — 2x/semana nos
    dias que não atrapalham a corrida, dose pelo nível, ciente do plano."""

    return StrengthRoutineBuilder.build(profile)
