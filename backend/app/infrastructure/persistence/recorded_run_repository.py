from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.core.clock import now_local


class RecordedRunRepository:
    """Acervo das corridas gravadas pelo GPS DENTRO do app (MVP). Fica separado
    do histórico de treino (Strava/Garmin) de propósito: não entra no ACWR/
    análise ainda, pra não duplicar a mesma corrida de quem sincroniza. Um
    arquivo por atleta: storage/recorded_runs/{profile}.json."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "recorded_runs"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            return []

    def add(self, profile: str, run: dict) -> dict:

        runs = self.load(profile)

        record = {
            "id": uuid.uuid4().hex[:12],
            "saved_at": now_local().isoformat(),
            "started_at": run.get("started_at"),
            "duration_s": int(run.get("duration_s") or 0),
            "distance_m": round(float(run.get("distance_m") or 0.0), 1),
            "avg_pace": run.get("avg_pace"),
            "points": run.get("points") or [],
        }

        runs.append(record)

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(runs, f, ensure_ascii=False, indent=2)

        return record
