import json
from pathlib import Path

from app.domain.entities.race_prediction import RacePrediction

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "race_predictions"
)


class RacePredictionRepository:
    """Estado ATUAL da previsão de prova do Garmin, por atleta —
    storage/race_predictions/{profile}.json. Um snapshot só (o mais recente):
    é estado que vale até o relógio recalcular, não série. Upsert simples."""

    def __init__(self):

        _STORAGE.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    def load(self, profile: str) -> RacePrediction | None:

        file = self._file(profile)

        if not file.exists():

            return None

        with open(file, encoding="utf-8") as f:

            return RacePrediction.from_dict(json.load(f))

    def save(self, profile: str, prediction: RacePrediction) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(prediction.to_dict(), f, ensure_ascii=False, indent=2)
