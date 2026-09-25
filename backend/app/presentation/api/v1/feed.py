from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.activity_comment_repository import (
    ActivityCommentRepository,
)
from app.infrastructure.persistence.activity_meta_repository import (
    ActivityMetaRepository,
    valid_key,
)
from app.infrastructure.persistence.activity_track_repository import (
    ActivityTrackRepository,
)
from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)
from app.infrastructure.persistence.workout_analysis_repository import (
    WorkoutAnalysisRepository,
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

    # segundos por km INTEIROS + divmod: evita o "5:60" (arredondar 59.6s -> 60
    # sem virar o minuto). round primeiro, depois separa minuto/segundo.
    total = round(moving_time_s / km)

    m, s = divmod(total, 60)

    return f"{m}:{s:02d}"


def _route_preview(points: list[dict] | None, n: int = 24) -> list[list[float]] | None:
    """Traçado LEVE (downsampled ~n pontos, [lat, lon] arredondado) pra a
    miniatura de mapa nos cards do feed — sem precisar puxar o traçado completo
    por atividade. Mantém início e fim. None quando não há pontos suficientes."""

    pts = [p for p in (points or []) if p.get("lat") and p.get("lon")]

    if len(pts) < 2:

        return None

    step = max(1, len(pts) // n)

    sampled = pts[::step]

    if sampled[-1] is not pts[-1]:

        sampled.append(pts[-1])

    return [[round(p["lat"], 5), round(p["lon"], 5)] for p in sampled]


def _run_date_iso(r: dict) -> str | None:

    for key in ("started_at", "saved_at"):

        v = r.get(key)

        if v:

            return str(v)[:10]

    return None


_GENERIC_NAMES = {
    "morning run", "afternoon run", "evening run", "night run", "lunch run",
    "corrida matinal", "corrida vespertina", "corrida noturna", "corrida",
}


def _name_score(name: str) -> int:
    """Qualidade do nome de uma atividade — pra escolher o melhor quando o MESMO
    treino chega em 2 fontes (Garmin e Strava). O nome do NOSSO plano
    ('Ritmind · ...') vence; o do Garmin costuma vir com prefixo de cidade e
    CORTADO ('São Paulo - Ritmind · Intervalado de Cruzei')."""

    n = (name or "").strip()

    score = min(len(n), 40)

    if n.startswith("Ritmind"):

        score += 100  # nome limpo do nosso plano

    low = n.lower()

    if low.startswith(("são ", "sao ")) or " - " in n[:16]:

        score -= 15  # prefixo de local do Garmin (e costuma vir cortado)

    if low in _GENERIC_NAMES:

        score -= 30

    return score


def _dedup_archived(items: list[dict]) -> list[dict]:
    """Junta o MESMO treino que veio de 2 fontes (Garmin + Strava = mesma data +
    distância ~igual, ids diferentes): fica com o melhor nome, garante o traçado
    se alguma cópia tiver e completa stats faltantes. Evita corrida duplicada no
    feed e o nome cortado. Ver [[project_garmin_strava_dedup]]."""

    out: list[dict] = []

    for it in items:

        dup = next(
            (
                o
                for o in out
                if o["date_iso"] == it["date_iso"]
                and abs(o["distance_km"] - it["distance_km"]) < 0.15
            ),
            None,
        )

        if dup is None:

            out.append(it)

            continue

        if _name_score(it["name"]) > _name_score(dup["name"]):

            dup["name"] = it["name"]

        if not dup["has_track"] and it["has_track"]:

            dup["has_track"] = it["has_track"]
            dup["track_source"] = it["track_source"]
            dup["track_id"] = it["track_id"]

        for k in ("avg_hr", "max_hr", "elevation_gain", "hr_zones", "hr_zone_floors", "air_temp_c", "pace"):

            if dup.get(k) is None and it.get(k) is not None:

                dup[k] = it[k]

    return out


def _zone_floors(profile: str, archived: list) -> list[int] | None:

    try:

        from app.application.history.hr_zone_resolver import HrZoneResolver
        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        zones = HrZoneResolver.for_profile(
            profile, RunnerProfileRepository().load(profile), archived
        )

        return list(zones.floors) if zones is not None else None

    except Exception as e:

        print(f"Feed: zonas de FC indisponíveis p/ {profile}: {e}")

        return None


def build_feed(profile: str) -> list[dict]:
    """Monta o feed de atividades de UM atleta (arquivadas + app, dedup, mais
    recentes primeiro). Reusado pela rota do próprio atleta e pelo social
    (perfil/atividades de outro atleta)."""

    archived = [
        a
        for a in ActivityArchiveRepository().load_activities(profile)
        if _is_run(a.sport)
    ]

    tracks = ActivityTrackRepository().load(profile)  # id_str -> {points,splits}

    # faixas de bpm da régua de zonas do atleta (a do relógio, quando há) —
    # o app mostra junto do tempo em cada zona
    zone_floors = _zone_floors(profile, archived)

    items: list[dict] = []

    for a in archived:

        has_arch_track = str(a.id) in tracks

        items.append(
            {
                "key": f"arch-{a.id}",
                "source": "sync",
                "datetime": a.start_date.isoformat(),
                "date_iso": a.start_date.date().isoformat(),
                "distance_km": round(a.distance / 1000, 2),
                "duration_min": round(a.moving_time / 60),
                "duration_s": round(a.moving_time),
                "pace": _pace(a.distance, a.moving_time),
                "avg_hr": int(a.average_heartrate) if a.average_heartrate else None,
                "max_hr": int(a.max_heartrate) if a.max_heartrate else None,
                "elevation_gain": round(a.elevation_gain) if a.elevation_gain else None,
                "hr_zones": a.hr_zone_minutes,
                "hr_zone_floors": zone_floors if a.hr_zone_minutes else None,
                "air_temp_c": round(a.air_temp_c) if a.air_temp_c is not None else None,
                "name": a.name,
                "has_track": has_arch_track,
                "track_source": "arch" if has_arch_track else None,
                "track_id": str(a.id) if has_arch_track else None,
                "route_preview": _route_preview(tracks[str(a.id)].get("points")) if has_arch_track else None,
            }
        )

    # mesmo treino em 2 fontes (Garmin+Strava) não aparece 2x e fica com o nome
    # limpo (não o cortado do Garmin)
    items = _dedup_archived(items)

    for r in RecordedRunRepository().load(profile):

        d_iso = _run_date_iso(r)

        if not d_iso:

            continue

        km = round((r.get("distance_m") or 0) / 1000, 2)

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

            if not match.get("route_preview"):

                match["route_preview"] = _route_preview(r.get("points"))

            continue

        items.append(
            {
                "key": f"app-{r['id']}",
                "source": "app",
                "datetime": r.get("started_at") or r.get("saved_at"),
                "date_iso": d_iso,
                "distance_km": km,
                "duration_min": round((r.get("duration_s") or 0) / 60),
                "duration_s": round(r.get("duration_s") or 0),
                "pace": r.get("avg_pace"),
                "avg_hr": None,
                "max_hr": None,
                "elevation_gain": None,
                "hr_zones": None,
                "hr_zone_floors": None,
                "air_temp_c": None,
                "name": "Corrida no app",
                "has_track": True,
                "track_source": "app",
                "track_id": r["id"],
                "route_preview": _route_preview(r.get("points")),
            }
        )

    # adornos do atleta: título custom (sobrepõe o nome) + foto (booleano; os
    # bytes só saem sob demanda no detalhe) + contador de comentários. Uma
    # leitura de cada por atleta.
    meta = ActivityMetaRepository().load(profile)
    comment_counts = ActivityCommentRepository().counts(profile)

    for it in items:

        entry = meta.get(it["key"]) or {}

        if entry.get("title"):

            it["name"] = entry["title"]
            it["custom_title"] = True

        it["has_photo"] = bool(entry.get("has_photo"))
        it["comment_count"] = comment_counts.get(it["key"], 0)

    items.sort(key=lambda x: x.get("datetime") or "", reverse=True)

    return items


@router.get("")
async def activity_feed(profile: str = Depends(current_profile)):
    """Feed de atividades (tipo Strava): TODAS as corridas — arquivadas (Strava/
    Garmin) + gravadas no app — mais recentes primeiro. Cada corrida do app é só
    mais uma base: dedup por CORRIDA (mesma data + distância ~igual); quando bate
    com uma arquivada, mantém os stats da arquivada (FC/altimetria) e ANEXA o
    traçado do app (run_id) — assim a mesma corrida não aparece 2x e ainda ganha
    mapa/parciais. Só o app tem traçado hoje; as arquivadas vêm com stats."""

    return {"activities": build_feed(profile)}


@router.get("/analysis")
async def activity_analysis(
    date: str,
    km: float | None = None,
    profile: str = Depends(current_profile),
):
    """Análise que o coach fez do treino daquele dia — pra tela da atividade no
    app. Casa por DATA (+ distância, quando informada) porque a mesma corrida
    chega com ids diferentes do Garmin/Strava e o feed faz dedup por data+
    distância. Devolve `{analysis: null}` quando ainda não há análise."""

    entry = WorkoutAnalysisRepository().find(profile, date, km)

    if entry is None:

        return {"analysis": None}

    return {
        "analysis": entry.get("analysis"),
        "workout_type": entry.get("workout_type"),
        "created_at": entry.get("created_at"),
    }


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
        "metrics": track.get("metrics"),
        "series": track.get("series"),
    }


# ---------------------------------------------------- adornos (título + foto)

def _can_view(me: str, owner: str) -> bool:
    """me sempre vê o próprio; pra outro, respeita o modo do perfil + seguir."""

    if me == owner:

        return True

    from app.infrastructure.persistence.social_graph_repository import (
        SocialGraphRepository,
    )
    from app.infrastructure.persistence.social_profile_repository import (
        SocialProfileRepository,
    )

    return SocialGraphRepository().can_view(
        me, owner, SocialProfileRepository().is_public(owner)
    )


class MetaTitleIn(BaseModel):
    key: str
    title: str | None = None


class PhotoIn(BaseModel):
    key: str
    data: str  # data URL da imagem (comprimida no cliente antes de subir)


@router.post("/meta")
async def set_activity_title(body: MetaTitleIn, profile: str = Depends(current_profile)):
    """Batiza uma atividade minha (título custom que sobrepõe o nome do feed).
    Título vazio remove o custom (volta ao nome original)."""

    if not valid_key(body.key):

        raise HTTPException(status_code=400, detail="chave inválida")

    ActivityMetaRepository().set_title(profile, body.key, body.title)

    return {"ok": True}


@router.post("/photo")
async def upload_activity_photo(body: PhotoIn, profile: str = Depends(current_profile)):
    """Anexa 1 foto à minha atividade. O cliente já manda comprimida; o servidor
    RE-comprime (≤1280px, JPEG q80) pra garantir disco leve (rodamos free)."""

    if not valid_key(body.key):

        raise HTTPException(status_code=400, detail="chave inválida")

    try:

        ActivityMetaRepository().set_photo(profile, body.key, body.data)

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))

    return {"ok": True}


@router.delete("/photo/{key}")
async def delete_activity_photo(key: str, profile: str = Depends(current_profile)):

    if not valid_key(key):

        raise HTTPException(status_code=400, detail="chave inválida")

    ActivityMetaRepository().delete_photo(profile, key)

    return {"ok": True}


@router.get("/photo")
async def get_activity_photo(
    key: str,
    owner: str | None = None,
    me: str = Depends(current_profile),
):
    """Foto de uma atividade como data URL (pro detalhe). Endpoint AUTENTICADO
    (o <img> do detalhe recebe a data URL, não a URL direta) e com a trava de
    privacidade do social — foto de perfil privado só pra seguidor aprovado.
    Sem `owner` = a minha própria atividade."""

    if not valid_key(key):

        raise HTTPException(status_code=400, detail="chave inválida")

    target = owner or me

    if not _can_view(me, target):

        raise HTTPException(status_code=403, detail="Perfil privado.")

    return {"photo": ActivityMetaRepository().photo_data_url(target, key)}


# ---------------------------------------------------------------- comentários

def _first_name(profile: str) -> str:

    from app.infrastructure.persistence.runner_profile_repository import (
        RunnerProfileRepository,
    )

    try:

        return (RunnerProfileRepository().load(profile).name or profile).split(" ")[0]

    except Exception:

        return profile


class CommentIn(BaseModel):
    key: str
    text: str
    owner: str | None = None


@router.get("/comments")
async def list_comments(key: str, owner: str | None = None, me: str = Depends(current_profile)):
    """Comentários de uma atividade (guardados sob o DONO). Trava de privacidade
    do social. Sem `owner` = a minha atividade."""

    if not valid_key(key):

        raise HTTPException(status_code=400, detail="chave inválida")

    target = owner or me

    if not _can_view(me, target):

        raise HTTPException(status_code=403, detail="Perfil privado.")

    return {"comments": ActivityCommentRepository().list(target, key), "me": me}


@router.post("/comments")
async def add_comment(body: CommentIn, me: str = Depends(current_profile)):
    """Comenta numa atividade (minha ou de quem eu posso ver). Avisa o dono
    quando não sou eu (central + push)."""

    if not valid_key(body.key):

        raise HTTPException(status_code=400, detail="chave inválida")

    text = (body.text or "").strip()

    if not text:

        raise HTTPException(status_code=400, detail="comentário vazio")

    target = body.owner or me

    if not _can_view(me, target):

        raise HTTPException(status_code=403, detail="Perfil privado.")

    comment = ActivityCommentRepository().add(target, body.key, me, _first_name(me), text)

    if target != me:

        try:

            from app.application.notifications.app_inbox import AppInbox
            from app.infrastructure.persistence.runner_profile_repository import (
                RunnerProfileRepository,
            )

            runner = RunnerProfileRepository().load(target)
            await AppInbox.deliver(
                runner,
                f"{_first_name(me)} comentou no seu treino: “{text[:80]}”",
                kind="social_comment",
            )

        except Exception as e:

            print(f"[feed] notif de comentário falhou p/ '{target}': {e}")

    return {"comment": comment}


@router.delete("/comments")
async def delete_comment(key: str, id: str, owner: str | None = None, me: str = Depends(current_profile)):
    """Apaga um comentário — o AUTOR dele ou o DONO da atividade."""

    if not valid_key(key):

        raise HTTPException(status_code=400, detail="chave inválida")

    ok = ActivityCommentRepository().delete(owner or me, key, id, me)

    if not ok:

        raise HTTPException(status_code=403, detail="Não dá pra apagar esse comentário.")

    return {"ok": True}
