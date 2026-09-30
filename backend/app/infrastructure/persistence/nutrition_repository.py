"""Persiste a nutrição do atleta (storage/nutrition/{profile}.json): leituras
de bioimpedância (histórico), preferências e o último plano alimentar gerado."""

import json
from pathlib import Path

MAX_READINGS = 60


class NutritionRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "nutrition"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict:

        file = self._file(profile)

        data: dict = {}

        if file.exists():

            try:

                with open(file, encoding="utf-8") as f:

                    data = json.load(f)

            except (json.JSONDecodeError, OSError):

                data = {}

        if not isinstance(data, dict):

            data = {}

        data.setdefault("readings", [])
        data.setdefault("settings", {})
        data.setdefault("plan", None)

        return data

    def save(self, profile: str, data: dict) -> None:

        data["readings"] = data.get("readings", [])[-MAX_READINGS:]

        tmp = self._file(profile).with_suffix(".tmp")

        with open(tmp, "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

        tmp.replace(self._file(profile))
