from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.onboarding.app_onboarding_service import (
    AppOnboardingService,
    OnboardingValidationError,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


class OnboardingPayload(BaseModel):
    """Dados do wizard do app (já estruturados). Campos opcionais dependem do
    caminho: quem já corre manda freq/km/pace; quem não corre manda mobility."""

    name: str
    age: int
    sex: str | None = None
    weight: float
    height: float
    days: list[int]  # índices 0=segunda .. 6=domingo
    goal: str

    target_race: str | None = None
    target_time: str | None = None
    race_date: str | None = None

    runs_today: bool = False
    runs_per_week: int | None = None
    typical_km: float | None = None
    pace_distance_km: float | None = None
    pace_minutes: float | None = None

    mobility: str | None = None
    continuous_run_minutes: float | None = None
    walk_speed_kmh: float | None = None

    external_coach: bool = False


@router.post("/complete")
async def complete_onboarding(
    body: OnboardingPayload,
    profile: str = Depends(current_profile),
):
    """Finaliza o cadastro do atleta logado (wizard do app): grava o perfil e
    gera o plano inicial. Só o dono da sessão mexe no próprio cadastro."""

    try:

        return await AppOnboardingService.complete(profile, body.model_dump())

    except OnboardingValidationError as e:

        raise HTTPException(status_code=422, detail=str(e)) from e
