from datetime import date as date_cls

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.application.races.race_intel_service import RaceIntelService
from app.application.races.race_service import RaceService
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/races", tags=["Races"])


@router.get("")
async def list_races(profile: str = Depends(current_profile)):
    """Provas do atleta (uma ou várias), da mais próxima pra mais distante.
    `is_anchor` marca a que ancora o plano; `past` marca as que já passaram."""

    return {"races": RaceService.list(profile)}


class RaceIn(BaseModel):

    name: str
    date: str  # ISO YYYY-MM-DD
    target_time: str | None = None


@router.post("")
async def add_race(
    body: RaceIn,
    background_tasks: BackgroundTasks,
    profile: str = Depends(current_profile),
):
    """Cadastra uma prova. A prova futura mais próxima passa a ancorar o plano
    (sem virar a semana atual — o caminho mirando ela sai na próxima geração)."""

    name = (body.name or "").strip()

    if not name:

        raise HTTPException(status_code=422, detail="Dá um nome pra prova.")

    if len(name) > 80:

        raise HTTPException(status_code=422, detail="Nome muito longo.")

    try:

        d = date_cls.fromisoformat((body.date or "").strip())

    except ValueError:

        raise HTTPException(status_code=422, detail="Data inválida (use AAAA-MM-DD).")

    if d.year < 2020 or d.year > 2100:

        raise HTTPException(status_code=422, detail="Data fora do intervalo.")

    target_time = (body.target_time or "").strip() or None

    if target_time and not any(c.isdigit() for c in target_time):

        raise HTTPException(status_code=422, detail="Tempo-alvo inválido (ex.: 0:50:00).")

    record = RaceService.add(profile, name, d.isoformat(), target_time)

    # pesquisa a prova na web em segundo plano (dossiê de percurso/clima pro
    # coach) — não atrasa a resposta; genérica ("10 km") é ignorada
    background_tasks.add_task(RaceIntelService.ensure, name, d.isoformat())

    return {"ok": True, "race": record}


@router.delete("/{race_id}")
async def delete_race(race_id: str, profile: str = Depends(current_profile)):
    """Remove uma prova. Se era a âncora, o plano passa a mirar a próxima prova
    futura (ou volta ao treino de base, se não sobrar nenhuma)."""

    ok = RaceService.remove(profile, race_id)

    if not ok:

        raise HTTPException(status_code=404, detail="Prova não encontrada.")

    return {"ok": True}
