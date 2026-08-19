"""Marca que oferecemos mandar o treino de PROVA pro Garmin (na semana da
prova). Um 'sim' vale por uma janela que cobre da oferta (semana da prova) até
o dia. storage/race_workout/pending/{profile}.json. Gitignored.

Guarda TAMBÉM que a prova JÁ FOI empurrada pro relógio (por data da prova), pra
o companheiro NÃO re-oferecer algo que já está lá (a queixa do Renato: a prova
já tinha sido mandada e o coach ofereceu de novo). storage/race_workout/sent/."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "race_workout" / "pending"
)

_SENT_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "race_workout" / "sent"
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

    # -- "a prova JÁ foi mandada pro relógio" (por data da prova) --------

    @staticmethod
    def _sent_file(profile: str) -> Path:

        return _SENT_STORAGE / f"{profile}.json"

    @staticmethod
    def mark_sent(profile: str, race_iso: str) -> None:
        """Registra que a prova DESTA data já foi empurrada pro relógio."""

        _SENT_STORAGE.mkdir(parents=True, exist_ok=True)

        RaceWorkoutOfferStore._sent_file(profile).write_text(
            json.dumps({"race": race_iso}), encoding="utf-8"
        )

    @staticmethod
    def already_sent(profile: str, race_iso: str) -> bool:
        """A prova DESTA data já está no relógio? (uma prova nova, com outra
        data, volta False — a oferta pode disparar pra ela)."""

        file = RaceWorkoutOfferStore._sent_file(profile)

        if not file.exists():

            return False

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            return data.get("race") == race_iso

        except (json.JSONDecodeError, ValueError, OSError):

            return False
