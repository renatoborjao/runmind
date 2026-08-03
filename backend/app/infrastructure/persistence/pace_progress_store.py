"""Marca-d'água do último VDOT pelo qual o atleta já foi AVISADO de que ficou
mais rápido — storage/pace_progress/{profile}.json. Evita reavisar a cada
semana: o aviso só sai quando a forma sobe além do último marco. Gitignored
(dado de atleta)."""

import json
from pathlib import Path


class PaceProgressStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "pace_progress"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def last_vdot(self, profile: str) -> float | None:

        file = self._file(profile)

        if not file.exists():

            return None

        try:

            return json.loads(file.read_text(encoding="utf-8")).get("last_vdot")

        except Exception:

            return None

    def save(self, profile: str, vdot: float) -> None:

        self._file(profile).write_text(
            json.dumps({"last_vdot": vdot}), encoding="utf-8"
        )
