import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/recorded-runs", tags=["RecordedRuns"])


def _haversine(a: dict, b: dict) -> float:
    """Distância em metros entre dois pontos lat/lon."""

    R = 6371000.0
    lat1, lon1, lat2, lon2 = map(
        math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]]
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _fmt_pace(sec_per_km: float) -> str:

    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def _splits(points: list[dict]) -> list[dict]:
    """Parciais por km a partir do traçado (distância por haversine, tempo pelo
    campo t de cada ponto). O último trecho parcial (>=300m) entra marcado."""

    if len(points) < 2:

        return []

    splits: list[dict] = []
    cum = 0.0
    next_mark = 1000.0
    prev = points[0]
    prev_t = float(prev.get("t") or 0)
    last_t = prev_t

    for p in points[1:]:

        d = _haversine(prev, p)
        t = float(p.get("t") if p.get("t") is not None else prev_t)
        seg_t = t - prev_t

        if d > 0 and cum + d >= next_mark:

            frac = (next_mark - cum) / d
            mark_t = prev_t + seg_t * frac
            splits.append({
                "km": int(next_mark / 1000),
                "sec": round(mark_t - last_t, 1),
                "pace": _fmt_pace(mark_t - last_t),
                "partial_km": None,
            })
            last_t = mark_t
            next_mark += 1000

        cum += d
        prev = p
        prev_t = t

    rem = cum - (next_mark - 1000)

    if rem >= 300:

        pk = rem / 1000
        sec = prev_t - last_t
        splits.append({
            "km": None,
            "sec": round(sec, 1),
            "pace": _fmt_pace(sec / pk) if pk > 0 else None,
            "partial_km": round(pk, 2),
        })

    return splits


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


@router.get("/{run_id}")
async def get_run(run_id: str, profile: str = Depends(current_profile)):
    """Detalhe de uma corrida gravada: dados + traçado (pontos) + parciais/km."""

    run = next(
        (r for r in RecordedRunRepository().load(profile) if r.get("id") == run_id),
        None,
    )

    if run is None:

        raise HTTPException(status_code=404, detail="Corrida não encontrada.")

    points = run.get("points") or []

    return {
        "id": run["id"],
        "saved_at": run.get("saved_at"),
        "started_at": run.get("started_at"),
        "duration_s": run.get("duration_s"),
        "distance_m": run.get("distance_m"),
        "avg_pace": run.get("avg_pace"),
        "points": points,
        "splits": _splits(points),
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
