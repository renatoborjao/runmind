"""Janela móvel do sinal de forma-sob-fadiga: as últimas N corridas quebraram a
cadência no fim? storage/form_fatigue/{profile}.json. `is_fading` = quebrou em
VÁRIAS das últimas (padrão, não um dia ruim). Gitignored (dado de atleta)."""

import json
from pathlib import Path

# quantas corridas recentes a janela guarda
_KEEP = 8

# quantas delas precisam ter quebrado pra virar sinal (padrão, não tropeço)
_MIN_FADES = 3


class FormFatigueStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "form_fatigue"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {"recent": [], "processed": []}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except Exception:

            return {"recent": [], "processed": []}

    def processed_ids(self, profile: str) -> set[int]:

        return set(self._load(profile).get("processed", []))

    def is_fading(self, profile: str) -> bool:

        recent = self._load(profile).get("recent", [])

        return sum(1 for f in recent if f) >= _MIN_FADES

    def record(self, profile: str, activity_id: int, faded: bool) -> None:

        data = self._load(profile)

        recent = list(data.get("recent", []))

        recent.append(bool(faded))

        recent = recent[-_KEEP:]

        processed = set(data.get("processed", []))

        processed.add(int(activity_id))

        self._file(profile).write_text(
            json.dumps({"recent": recent, "processed": sorted(processed)}),
            encoding="utf-8",
        )
