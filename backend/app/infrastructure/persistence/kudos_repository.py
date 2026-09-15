"""Kudos (curtidas) por atividade. Guardado no DONO da atividade:
storage/kudos/{owner}.json -> {activity_key: [profile_ids]}. Best-effort."""

from __future__ import annotations

import json
from pathlib import Path


class KudosRepository:

    def __init__(self):

        self.storage = Path(__file__).resolve().parents[3] / "storage" / "kudos"

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, owner: str) -> Path:

        return self.storage / f"{owner}.json"

    def load(self, owner: str) -> dict:

        file = self._file(owner)

        if not file.exists():

            return {}

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            return {}

    def toggle(self, owner: str, activity_key: str, me: str) -> bool:
        """Liga/desliga o kudos de `me` na atividade. Devolve True se ficou curtido."""

        data = self.load(owner)

        givers = data.get(activity_key, [])

        if me in givers:

            givers.remove(me)
            liked = False

        else:

            givers.append(me)
            liked = True

        data[activity_key] = givers

        with open(self._file(owner), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

        return liked

    def givers(self, owner: str, activity_key: str) -> list[str]:

        return list(self.load(owner).get(activity_key, []))
