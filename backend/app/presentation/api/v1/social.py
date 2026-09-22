"""Camada social (estilo Strava): descobrir atletas, seguir/solicitar, ver
perfil e atividades de outros, feed de quem eu sigo e kudos. Privacidade: cada
atleta define o modo do perfil (público × com solicitação) — atividades de
perfil privado só aparecem pra seguidor aprovado. Toda ação relevante avisa o
outro atleta (central do app + push), reusando o [[AppInbox]]."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.notifications.app_inbox import AppInbox
from app.infrastructure.persistence.kudos_repository import KudosRepository
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.social_graph_repository import (
    SocialGraphRepository,
)
from app.infrastructure.persistence.social_profile_repository import (
    SocialProfileRepository,
)
from app.presentation.api.deps import current_profile
from app.presentation.api.v1.feed import build_feed

router = APIRouter(prefix="/social", tags=["Social"])


def _card(profile: str, me: str, graph: SocialGraphRepository, sp: SocialProfileRepository) -> dict:
    """Cartão público de um atleta pra listas (descobrir/seguidores)."""

    try:

        r = RunnerProfileRepository().load(profile)
        name = r.name or profile
        avatar = r.avatar

    except Exception:

        name, avatar = profile, None

    return {
        "id": profile,
        "name": name,
        "avatar": avatar,
        "privacy": sp.get(profile).get("privacy"),
        "relationship": graph.relationship(me, profile),
    }


def _journey(items: list[dict]) -> dict:

    runs = [it for it in items]

    if not runs:

        return {"km_total": 0, "runs": 0, "biggest_km": 0}

    kms = [it["distance_km"] for it in runs]

    return {
        "km_total": round(sum(kms)),
        "runs": len(runs),
        "biggest_km": round(max(kms), 1),
    }


def _kudos_view(owner: str, key: str, me: str, kudos: KudosRepository) -> dict:

    givers = kudos.givers(owner, key)

    return {"kudos": len(givers), "kudos_by_me": me in givers}


async def _notify(target: str, message: str, kind: str) -> None:
    """Toca o outro atleta (central + push). Best-effort — nunca derruba a ação."""

    try:

        runner = RunnerProfileRepository().load(target)
        await AppInbox.deliver(runner, message, kind=kind)

    except Exception as e:

        print(f"[social] notif falhou p/ '{target}': {e}")


def _first_name(profile: str) -> str:

    try:

        return (RunnerProfileRepository().load(profile).name or profile).split(" ")[0]

    except Exception:

        return profile


# ---------------------------------------------------------------- descobrir

@router.get("/athletes")
async def athletes(me: str = Depends(current_profile)):
    """Diretório de atletas pra descobrir e seguir (todos menos eu)."""

    graph, sp = SocialGraphRepository(), SocialProfileRepository()

    out = [
        _card(p, me, graph, sp)
        for p in RunnerProfileRepository().list_all()
        if p != me
    ]

    out.sort(key=lambda c: (c["name"] or "").lower())

    return {"athletes": out}


@router.get("/me")
async def my_social(me: str = Depends(current_profile)):

    sp = SocialProfileRepository().get(me)
    counts = SocialGraphRepository().counts(me)

    return {"privacy": sp.get("privacy"), "bio": sp.get("bio", ""), **counts}


class SocialPatch(BaseModel):
    privacy: str | None = None
    bio: str | None = None


@router.put("/me")
async def set_my_social(body: SocialPatch, me: str = Depends(current_profile)):

    data = SocialProfileRepository().set(me, privacy=body.privacy, bio=body.bio)

    return {"privacy": data.get("privacy"), "bio": data.get("bio", "")}


# ---------------------------------------------------------------- pedidos

@router.get("/requests")
async def incoming_requests(me: str = Depends(current_profile)):

    graph, sp = SocialGraphRepository(), SocialProfileRepository()

    reqs = graph.load(me)["requests_in"]

    return {"requests": [_card(p, me, graph, sp) for p in reqs]}


@router.post("/requests/{other}/accept")
async def accept_request(other: str, me: str = Depends(current_profile)):

    if not SocialGraphRepository().accept(me, other):

        raise HTTPException(status_code=404, detail="Sem pedido desse atleta.")

    await _notify(
        other,
        f"{_first_name(me)} aceitou seu pedido — agora você segue e vê os treinos. 🏃",
        "social_accept",
    )

    return {"ok": True}


@router.post("/requests/{other}/reject")
async def reject_request(other: str, me: str = Depends(current_profile)):

    if not SocialGraphRepository().reject(me, other):

        raise HTTPException(status_code=404, detail="Sem pedido desse atleta.")

    return {"ok": True}


# ---------------------------------------------------------------- seguir

@router.post("/follow/{other}")
async def follow(other: str, me: str = Depends(current_profile)):

    if other == me:

        raise HTTPException(status_code=400, detail="Não dá pra seguir você mesmo.")

    if other not in RunnerProfileRepository().list_all():

        raise HTTPException(status_code=404, detail="Atleta não encontrado.")

    public = SocialProfileRepository().is_public(other)

    state = SocialGraphRepository().follow(me, other, public)

    if state == "following":

        await _notify(other, f"{_first_name(me)} começou a te seguir. 👋", "social_follow")

    elif state == "requested":

        await _notify(other, f"{_first_name(me)} pediu pra te seguir.", "social_request")

    return {"relationship": state}


@router.post("/unfollow/{other}")
async def unfollow(other: str, me: str = Depends(current_profile)):

    SocialGraphRepository().unfollow(me, other)

    return {"relationship": "none"}


# ---------------------------------------------------------------- perfil

@router.get("/athletes/{other}")
async def athlete_profile(other: str, me: str = Depends(current_profile)):

    if other not in RunnerProfileRepository().list_all():

        raise HTTPException(status_code=404, detail="Atleta não encontrado.")

    graph, sp = SocialGraphRepository(), SocialProfileRepository()
    settings = sp.get(other)
    public = settings.get("privacy") == "public"
    can_view = graph.can_view(me, other, public)

    card = _card(other, me, graph, sp)
    counts = graph.counts(other)

    # eles me seguem? (pra mostrar "segue você")
    follows_me = me in graph.load(other)["following"]

    journey = _journey(build_feed(other)) if can_view else None

    return {
        **card,
        "bio": settings.get("bio", ""),
        "counts": counts,
        "follows_me": follows_me,
        "can_view": can_view,
        "journey": journey,
    }


@router.get("/athletes/{other}/activities")
async def athlete_activities(other: str, me: str = Depends(current_profile)):

    graph, sp = SocialGraphRepository(), SocialProfileRepository()
    public = sp.is_public(other)

    if not graph.can_view(me, other, public):

        raise HTTPException(status_code=403, detail="Perfil privado. Siga pra ver.")

    kudos = KudosRepository()
    items = build_feed(other)

    for it in items:

        it.update(_kudos_view(other, it["key"], me, kudos))
        it["owner"] = other

    return {"activities": items}


@router.get("/athletes/{other}/track/{source}/{track_id}")
async def athlete_track(other: str, source: str, track_id: str, me: str = Depends(current_profile)):
    """Traçado (mapa + splits + métricas + séries) de uma atividade de OUTRO
    atleta — respeitando a privacidade. source: 'app' (recorded-run) ou 'arch'."""

    graph, sp = SocialGraphRepository(), SocialProfileRepository()

    if not graph.can_view(me, other, sp.is_public(other)):

        raise HTTPException(status_code=403, detail="Perfil privado.")

    if source == "app":

        from app.presentation.api.v1.recorded_runs import recorded_run_detail

        d = recorded_run_detail(other, track_id)

        if not d:

            raise HTTPException(status_code=404, detail="Sem traçado.")

        return {"points": d.get("points", []), "splits": d.get("splits", [])}

    from app.infrastructure.persistence.activity_track_repository import (
        ActivityTrackRepository,
    )

    track = ActivityTrackRepository().get(other, track_id)

    if track is None:

        raise HTTPException(status_code=404, detail="Sem traçado.")

    return {
        "points": track.get("points", []),
        "splits": track.get("splits", []),
        "metrics": track.get("metrics"),
        "series": track.get("series"),
    }


# ---------------------------------------------------------------- feed social

@router.get("/feed")
async def following_feed(me: str = Depends(current_profile)):
    """Atividades recentes de quem EU sigo (tela social), com dono e kudos."""

    graph, sp, kudos = SocialGraphRepository(), SocialProfileRepository(), KudosRepository()

    following = graph.load(me)["following"]

    cards = {p: _card(p, me, graph, sp) for p in following}

    items: list[dict] = []

    for p in following:

        if not graph.can_view(me, p, sp.is_public(p)):

            continue

        for it in build_feed(p)[:8]:  # últimas de cada um

            it.update(_kudos_view(p, it["key"], me, kudos))
            it["owner"] = p
            it["owner_name"] = cards[p]["name"]
            it["owner_avatar"] = cards[p]["avatar"]
            items.append(it)

    items.sort(key=lambda x: x.get("datetime") or "", reverse=True)

    return {"activities": items[:60]}


# ---------------------------------------------------------------- kudos

class KudosBody(BaseModel):
    owner: str
    key: str


@router.post("/kudos")
async def toggle_kudos(body: KudosBody, me: str = Depends(current_profile)):

    graph, sp = SocialGraphRepository(), SocialProfileRepository()

    if not graph.can_view(me, body.owner, sp.is_public(body.owner)):

        raise HTTPException(status_code=403, detail="Você não pode ver essa atividade.")

    liked = KudosRepository().toggle(body.owner, body.key, me)

    if liked and body.owner != me:

        await _notify(body.owner, f"{_first_name(me)} te mandou um Rit no seu treino. 🏃", "social_kudos")

    return {"liked": liked}
