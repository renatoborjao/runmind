from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/recorded-runs", tags=["RecordedRuns"])


class Point(BaseModel):

    lat: float
    lon: float
    t: int | None = None  # segundos desde o início


class RunIn(BaseModel):

    started_at: str | None = None
    duration_s: int
    distance_m: float
    avg_pace: str | None = None
    points: list[Point] = []


@router.get("")
async def list_runs(profile: str = Depends(current_profile)):

    runs = RecordedRunRepository().load(profile)

    # mais recentes primeiro; não devolve os pontos (payload leve na lista)
    return {
        "runs": [
            {k: v for k, v in r.items() if k != "points"}
            for r in sorted(runs, key=lambda x: x.get("saved_at", ""), reverse=True)
        ]
    }


@router.post("")
async def save_run(body: RunIn, profile: str = Depends(current_profile)):

    if body.distance_m <= 0 or body.duration_s <= 0:

        raise HTTPException(status_code=400, detail="corrida vazia")

    record = RecordedRunRepository().add(
        profile,
        {
            "started_at": body.started_at,
            "duration_s": body.duration_s,
            "distance_m": body.distance_m,
            "avg_pace": body.avg_pace,
            "points": [p.model_dump() for p in body.points],
        },
    )

    return {"ok": True, "id": record["id"]}
