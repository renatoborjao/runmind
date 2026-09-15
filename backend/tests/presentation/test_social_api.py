from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.infrastructure.security.session_token import SessionToken
from app.main import app

client = TestClient(app)
MOD = "app.presentation.api.v1.social"

ATHLETES = {
    "ana": SimpleNamespace(id="ana", name="Ana Silva", avatar=None),
    "bru": SimpleNamespace(id="bru", name="Bruno Costa", avatar=None),
}


def _runner_repo():
    return SimpleNamespace(
        list_all=lambda: list(ATHLETES.keys()),
        load=lambda p: ATHLETES[p],
    )


def _ctx(tmp_path):
    from app.infrastructure.persistence.social_graph_repository import (
        SocialGraphRepository,
    )
    from app.infrastructure.persistence.social_profile_repository import (
        SocialProfileRepository,
    )
    from app.infrastructure.persistence.kudos_repository import KudosRepository

    (tmp_path / "graph").mkdir()
    (tmp_path / "prof").mkdir()
    (tmp_path / "kudos").mkdir()

    def graph():
        r = SocialGraphRepository()
        r.storage = tmp_path / "graph"
        return r

    def prof():
        r = SocialProfileRepository()
        r.storage = tmp_path / "prof"
        return r

    def kudos():
        r = KudosRepository()
        r.storage = tmp_path / "kudos"
        return r

    async def _noop(*a, **k):
        return None

    return [
        patch(f"{MOD}.SocialGraphRepository", graph),
        patch(f"{MOD}.SocialProfileRepository", prof),
        patch(f"{MOD}.KudosRepository", kudos),
        patch(f"{MOD}.RunnerProfileRepository", _runner_repo),
        patch(f"{MOD}.AppInbox.deliver", _noop),
        patch(f"{MOD}.build_feed", lambda p: [
            {"key": f"arch-{p}1", "distance_km": 10.0, "datetime": "2026-09-10T07:00:00", "name": "Corrida"},
        ]),
    ]


def _auth(profile):
    return {"rm_session": SessionToken.issue(profile)}


def test_public_follow_and_kudos_flow(tmp_path):
    with _apply(_ctx(tmp_path)):
        # ana segue bru (público por padrão) -> following na hora
        r = client.post("/api/v1/social/follow/bru", cookies=_auth("ana"))
        assert r.status_code == 200
        assert r.json()["relationship"] == "following"

        # perfil do bru pela ana: pode ver, relationship following
        r = client.get("/api/v1/social/athletes/bru", cookies=_auth("ana"))
        assert r.status_code == 200
        body = r.json()
        assert body["relationship"] == "following"
        assert body["can_view"] is True
        assert body["counts"]["followers"] == 1

        # atividades do bru visíveis
        r = client.get("/api/v1/social/athletes/bru/activities", cookies=_auth("ana"))
        assert r.status_code == 200
        acts = r.json()["activities"]
        assert len(acts) == 1
        key = acts[0]["key"]

        # kudos toggle
        r = client.post("/api/v1/social/kudos", json={"owner": "bru", "key": key}, cookies=_auth("ana"))
        assert r.json()["liked"] is True

        # feed de quem ana segue mostra a corrida do bru com kudos
        r = client.get("/api/v1/social/feed", cookies=_auth("ana"))
        feed = r.json()["activities"]
        assert len(feed) == 1
        assert feed[0]["owner"] == "bru"
        assert feed[0]["kudos"] == 1
        assert feed[0]["kudos_by_me"] is True


def test_private_profile_requires_approval(tmp_path):
    with _apply(_ctx(tmp_path)):
        # bru vira privado
        r = client.put("/api/v1/social/me", json={"privacy": "private"}, cookies=_auth("bru"))
        assert r.json()["privacy"] == "private"

        # ana tenta seguir -> vira pedido
        r = client.post("/api/v1/social/follow/bru", cookies=_auth("ana"))
        assert r.json()["relationship"] == "requested"

        # atividades bloqueadas enquanto não aprovado
        r = client.get("/api/v1/social/athletes/bru/activities", cookies=_auth("ana"))
        assert r.status_code == 403

        # bru vê o pedido e aceita
        r = client.get("/api/v1/social/requests", cookies=_auth("bru"))
        assert [c["id"] for c in r.json()["requests"]] == ["ana"]

        r = client.post("/api/v1/social/requests/ana/accept", cookies=_auth("bru"))
        assert r.status_code == 200

        # agora ana vê
        r = client.get("/api/v1/social/athletes/bru/activities", cookies=_auth("ana"))
        assert r.status_code == 200


class _apply:
    """Aplica uma lista de context managers (patches) como um só."""

    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.__enter__()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.__exit__(*exc)
        return False
