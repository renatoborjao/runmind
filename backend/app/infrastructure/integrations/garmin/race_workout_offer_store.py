"""Marca que oferecemos mandar o treino de PROVA pro Garmin (na semana da
prova). Um 'sim' vale por uma janela que cobre da oferta (semana da prova) até
o dia. storage/race_workout/pending/{profile}.json. Gitignored."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "race_workout" / "pending"
)

# a oferta sai na semana da prova (~7 dias antes); vale até o dia da prova
_TTL_SECONDS = 8 * 24 * 3600


class RaceWorkoutOfferStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(profile: str) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        RaceWorkoutOfferStore._file(profile).write_text(
            json.dumps({"ts": time.time()}), encoding="utf-8"
        )

    @staticmethod
    def is_pending(profile: str) -> bool:

        file = RaceWorkoutOfferStore._file(profile)

        if not file.exists():

            return False

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            return (time.time() - data["ts"]) < _TTL_SECONDS

        except (json.JSONDecodeError, KeyError, ValueError, OSError):

            return False

    @staticmethod
    def clear(profile: str) -> None:

        file = RaceWorkoutOfferStore._file(profile)

        if file.exists():

            file.unlink()
