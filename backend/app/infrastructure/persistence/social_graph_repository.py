"""Grafo social: quem segue quem + pedidos pendentes (perfil com solicitação).
Um arquivo por atleta: storage/social_graph/{profile}.json com
{following, followers, requests_in, requests_out}. As duas pontas de cada aresta
são gravadas (ex.: seguir A→B escreve following de A e followers de B), pra
leitura ser barata dos dois lados. Best-effort."""

from __future__ import annotations

import json
from pathlib import Path

_EMPTY = {"following": [], "followers": [], "requests_in": [], "requests_out": []}


class SocialGraphRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "social_graph"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {k: [] for k in _EMPTY}

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

            return {k: list(data.get(k, [])) for k in _EMPTY}

        except (json.JSONDecodeError, OSError):

            return {k: [] for k in _EMPTY}

    def _save(self, profile: str, data: dict) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _add(lst: list, who: str) -> None:

        if who not in lst:

            lst.append(who)

    @staticmethod
    def _rm(lst: list, who: str) -> None:

        if who in lst:

            lst.remove(who)

    # ------------------------------------------------------------------

    def follow(self, me: str, other: str, other_is_public: bool) -> str:
        """Segue (público) ou manda pedido (privado). Devolve o novo estado:
        'following' ou 'requested'. Idempotente."""

        if me == other:

            return "self"

        a, b = self.load(me), self.load(other)

        if other in a["following"]:

            return "following"

        if other_is_public:

            self._add(a["following"], other)
            self._rm(a["requests_out"], other)
            self._add(b["followers"], me)
            self._rm(b["requests_in"], me)
            self._save(me, a)
            self._save(other, b)

            return "following"

        # privado: cria pedido
        self._add(a["requests_out"], other)
        self._add(b["requests_in"], me)
        self._save(me, a)
        self._save(other, b)

        return "requested"

    def unfollow(self, me: str, other: str) -> None:
        """Deixa de seguir E cancela qualquer pedido pendente entre os dois."""

        a, b = self.load(me), self.load(other)

        self._rm(a["following"], other)
        self._rm(a["requests_out"], other)
        self._rm(b["followers"], me)
        self._rm(b["requests_in"], me)

        self._save(me, a)
        self._save(other, b)

    def accept(self, me: str, requester: str) -> bool:
        """Eu (me) aceito o pedido de `requester` pra me seguir."""

        a = self.load(me)

        if requester not in a["requests_in"]:

            return False

        b = self.load(requester)

        self._rm(a["requests_in"], requester)
        self._add(a["followers"], requester)
        self._rm(b["requests_out"], me)
        self._add(b["following"], me)

        self._save(me, a)
        self._save(requester, b)

        return True

    def reject(self, me: str, requester: str) -> bool:

        a = self.load(me)

        if requester not in a["requests_in"]:

            return False

        b = self.load(requester)

        self._rm(a["requests_in"], requester)
        self._rm(b["requests_out"], me)

        self._save(me, a)
        self._save(requester, b)

        return True

    # ------------------------------------------------------------------

    def relationship(self, me: str, other: str) -> str:
        """Como EU me relaciono com `other`: self / following / requested / none."""

        if me == other:

            return "self"

        a = self.load(me)

        if other in a["following"]:

            return "following"

        if other in a["requests_out"]:

            return "requested"

        return "none"

    def can_view(self, viewer: str, owner: str, owner_is_public: bool) -> bool:
        """Viewer pode ver as ATIVIDADES de owner? Dono sempre; perfil público
        sempre; privado só pra seguidor aprovado."""

        if viewer == owner or owner_is_public:

            return True

        return viewer in self.load(owner)["followers"]

    def counts(self, profile: str) -> dict:

        d = self.load(profile)

        return {"following": len(d["following"]), "followers": len(d["followers"])}
