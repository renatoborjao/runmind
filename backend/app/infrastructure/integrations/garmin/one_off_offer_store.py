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
            json.dumps(
                {
                    "ts": time.time(),
                    "date": on_date.isoformat(),
                    "reminded": False,
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _read(profile: str) -> dict | None:
        """Payload da oferta se ainda VÁLIDA (dentro do TTL), senão None.
        Tolera o formato legado {ts, date} sem 'reminded'."""

        file = OneOffOfferStore._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            if (time.time() - data["ts"]) >= _TTL_SECONDS:

                return None

            date.fromisoformat(data["date"])  # valida

            return data

        except (json.JSONDecodeError, KeyError, ValueError, OSError, TypeError):

            return None

    @staticmethod
    def pending_date(profile: str) -> date | None:
        """Data do treino avulso ofertado, se ainda válida; senão None."""

        data = OneOffOfferStore._read(profile)

        return date.fromisoformat(data["date"]) if data else None

    @staticmethod
    def reminder_due(profile: str, min_age_seconds: float) -> bool:
        """Há avulso ofertado, com idade >= min_age (teve tempo de responder) e
        que AINDA não foi lembrado — 'montou o avulso e não confirmou o envio'."""

        data = OneOffOfferStore._read(profile)

        if data is None or data.get("reminded"):

            return False

        return (time.time() - data["ts"]) >= min_age_seconds

    @staticmethod
    def mark_reminded(profile: str) -> None:
        """UM lembrete por oferta; a oferta segue válida pro 'sim' seguinte."""

        data = OneOffOfferStore._read(profile)

        if data is None:

            return

        data["reminded"] = True

        OneOffOfferStore._file(profile).write_text(
            json.dumps(data), encoding="utf-8"
        )

    @staticmethod
    def clear(profile: str) -> None:

        file = OneOffOfferStore._file(profile)

        if file.exists():

            file.unlink()
