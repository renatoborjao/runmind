from fastapi import APIRouter, Depends, HTTPException

from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.activity_track_repository import (
    ActivityTrackRepository,
)
from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/feed", tags=["Feed"])

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    return any(h in (sport or "").lower() for h in _RUN_HINT)


def _pace(distance_m: float, moving_time_s: int) -> str | None:

    km = distance_m / 1000

    if km <= 0 or not moving_time_s:

        return None

    p = (moving_time_s / 60) / km

    return f"{int(p)}:{int(round((p % 1) * 60)):02d}"


def _run_date_iso(r: dict) -> str | None:

    for key in ("started_at", "saved_at"):

        v = r.get(key)

        if v:

            return str(v)[:10]

    return None


@router.get("")
async def activity_feed(profile: str = Depends(current_profile)):
    """Feed de atividades (tipo Strava): TODAS as corridas — arquivadas (Strava/
    Garmin) + gravadas no app — mais recentes primeiro. Cada corrida do app é só
    mais uma base: dedup por CORRIDA (mesma data + distância ~igual); quando bate
    com uma arquivada, mantém os stats da arquivada (FC/altimetria) e ANEXA o
    traçado do app (run_id) — assim a mesma corrida não aparece 2x e ainda ganha
    mapa/parciais. Só o app tem traçado hoje; as arquivadas vêm com stats."""

    archived = [
        a
        for a in ActivityArchiveRepository().load_activities(profile)
        if _is_run(a.sport)
    ]

    tracks = ActivityTrackRepository().load(profile)  # id_str -> {points,splits}

    items: list[dict] = []

    for a in archived:

        has_arch_track = str(a.id) in tracks

        items.append(
            {
                "key": f"arch-{a.id}",
                "source": "sync",
                "datetime": a.start_date.isoformat(),
                "date_iso": a.start_date.date().isoformat(),
                "distance_km": round(a.distance / 1000, 1),
                "duration_min": round(a.moving_time / 60),
                "pace": _pace(a.distance, a.moving_time),
                "avg_hr": int(a.average_heartrate) if a.average_heartrate else None,
                "max_hr": int(a.max_heartrate) if a.max_heartrate else None,
                "elevation_gain": round(a.elevation_gain) if a.elevation_gain else None,
                "hr_zones": a.hr_zone_minutes,
                "air_temp_c": round(a.air_temp_c) if a.air_temp_c is not None else None,
                "name": a.name,
                "has_track": has_arch_track,
                "track_source": "arch" if has_arch_track else None,
                "track_id": str(a.id) if has_arch_track else None,
            }
        )

    for r in RecordedRunRepository().load(profile):

        d_iso = _run_date_iso(r)

        if not d_iso:

            continue

        km = round((r.get("distance_m") or 0) / 1000, 1)

        # mesma corrida já veio de outra base? anexa o traçado nela, não duplica
        match = next(
            (
                it
                for it in items
                if it["date_iso"] == d_iso and abs(it["distance_km"] - km) < 0.6
            ),
            None,
        )

        if match is not None:

            # mesma corrida: mantém os stats da arquivada e anexa o traçado do
            # app (tem pontos km-a-km, mais rico que o polyline resumido)
            match["has_track"] = True
            match["track_source"] = "app"
            match["track_id"] = r["id"]

            continue

        items.append(
            {
                "key": f"app-{r['id']}",
                "source": "app",
                "datetime": r.get("started_at") or r.get("saved_at"),
                "date_iso": d_iso,
                "distance_km": km,
                "duration_min": round((r.get("duration_s") or 0) / 60),
                "pace": r.get("avg_pace"),
                "avg_hr": None,
                "max_hr": None,
                "elevation_gain": None,
                "hr_zones": None,
                "air_temp_c": None,
                "name": "Corrida no app",
                "has_track": True,
                "track_source": "app",
                "track_id": r["id"],
            }
        )

    items.sort(key=lambda x: x.get("datetime") or "", reverse=True)

    return {"activities": items}


@router.get("/track/{activity_id}")
async def activity_track(activity_id: str, profile: str = Depends(current_profile)):
    """Traçado (pontos + parciais) de uma atividade sincronizada (Strava/Garmin)
    guardado no acervo de traçados. Corridas do app vêm por /recorded-runs/{id}."""

    track = ActivityTrackRepository().get(profile, activity_id)

    if track is None:

        raise HTTPException(status_code=404, detail="Sem traçado pra esta atividade.")

    return {
        "points": track.get("points", []),
        "splits": track.get("splits", []),
    }
