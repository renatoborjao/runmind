from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.application.home.calendar_builder import CalendarBuilder
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/calendar", tags=["Calendar"])


@router.get("")
async def get_month(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    profile: str = Depends(current_profile),
):
    """Treinos executados + planejados futuros + prova do mês pedido."""

    try:

        return CalendarBuilder.month(profile, year, month)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/day")
async def get_day(
    date_iso: str = Query(alias="date"),
    profile: str = Depends(current_profile),
):
    """Detalhe de um dia: planejado × executado."""

    try:

        date.fromisoformat(date_iso)

    except ValueError:

        raise HTTPException(status_code=400, detail="data inválida (use YYYY-MM-DD)")

    try:

        return CalendarBuilder.day(profile, date_iso)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
