"""Marca-d'água do melhor VDOT CONTÍNUO do atleta (dos best_efforts do Strava)
+ os ids de corrida já processados (pra não rebaixar o Strava de novo).
storage/best_effort_vdot/{profile}.json. Gitignored (dado de atleta)."""

import json
from pathlib import Path


class BestEffortVdotStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "best_effort_vdot"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {"max_vdot": None, "processed": []}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except Exception:

            return {"max_vdot": None, "processed": []}

    def max_vdot(self, profile: str) -> float | None:

        return self._load(profile).get("max_vdot")

    def processed_ids(self, profile: str) -> set[int]:

        return set(self._load(profile).get("processed", []))

    def update(self, profile: str, activity_id: int, vdot: float | None) -> None:
        """Marca a corrida como processada e sobe a marca-d'água se o VDOT do
        esforço contínuo dela for o novo máximo. `vdot` None só marca o id."""

        data = self._load(profile)

        processed = set(data.get("processed", []))

        processed.add(int(activity_id))

        current = data.get("max_vdot")

        if vdot is not None and (current is None or vdot > current):

            current = round(vdot, 1)

        self._file(profile).write_text(
            json.dumps({"max_vdot": current, "processed": sorted(processed)}),
            encoding="utf-8",
        )
