"""Marca-d'água do último nível pelo qual o atleta já foi AVISADO de que ficou
mais rápido — storage/pace_progress/{profile}.json. Evita reavisar a cada
semana: o aviso só sai quando a forma sobe além do último marco.

Guarda DOIS marcos: o VDOT (capacidade, sobe com o teto) e o fácil (`easy_min`,
que evolui pela âncora de realidade das corridas recentes mesmo com VDOT
estável — ver [[project_modelo_pace_vdot]]). Gitignored (dado de atleta).
Retrocompatível: arquivo antigo só com `last_vdot` → `last_easy_min` = None."""

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

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except Exception:

            return {}

    def last_vdot(self, profile: str) -> float | None:

        return self._load(profile).get("last_vdot")

    def last_easy_min(self, profile: str) -> float | None:

        return self._load(profile).get("last_easy_min")

    def save(
        self,
        profile: str,
        vdot: float,
        easy_min: float | None = None,
    ) -> None:

        self._file(profile).write_text(
            json.dumps({"last_vdot": vdot, "last_easy_min": easy_min}),
            encoding="utf-8",
        )
