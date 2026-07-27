"""Marca que oferecemos mandar um treino AVULSO pro Garmin. Guarda também a
DATA do treino, porque o push escopado precisa saber qual dia empurrar. Um
'sim' vale por uma janela curta (a oferta é do treino que acabou de sair)."""

import json
import time
from datetime import date
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "one_off" / "pending"
)

# a oferta expira: um "sim" muito depois não deve sincronizar sozinho
_TTL_SECONDS = 12 * 3600


class OneOffOfferStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(profile: str, on_date: date) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        OneOffOfferStore._file(profile).write_text(
            json.dumps({"ts": time.time(), "date": on_date.isoformat()}),
            encoding="utf-8",
        )

    @staticmethod
    def pending_date(profile: str) -> date | None:
        """Data do treino avulso ofertado, se ainda válida; senão None."""

        file = OneOffOfferStore._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            fresh = (time.time() - data["ts"]) < _TTL_SECONDS

            return date.fromisoformat(data["date"]) if fresh else None

        except (json.JSONDecodeError, KeyError, ValueError, OSError):

            return None

    @staticmethod
    def clear(profile: str) -> None:

        file = OneOffOfferStore._file(profile)

        if file.exists():

            file.unlink()
