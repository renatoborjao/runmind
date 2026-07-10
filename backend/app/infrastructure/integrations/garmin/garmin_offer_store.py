"""Marca que oferecemos ao atleta mandar os treinos pro Garmin (na entrega
do plano). Assim, quando ele responder "SIM", sabemos que o sim é sobre o
Garmin — e não uma afirmação solta. Vale por uma janela curta (a oferta é do
plano recém-enviado)."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "garmin" / "pending"
)

# a oferta expira: um "sim" dias depois não deve sincronizar sozinho
_TTL_SECONDS = 48 * 3600


class GarminOfferStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(profile: str) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        GarminOfferStore._file(profile).write_text(
            json.dumps({"ts": time.time()}),
            encoding="utf-8",
        )

    @staticmethod
    def is_pending(profile: str) -> bool:

        file = GarminOfferStore._file(profile)

        if not file.exists():

            return False

        try:

            ts = json.loads(file.read_text(encoding="utf-8"))["ts"]

        except (json.JSONDecodeError, KeyError, OSError):

            return False

        return (time.time() - ts) < _TTL_SECONDS

    @staticmethod
    def clear(profile: str) -> None:

        file = GarminOfferStore._file(profile)

        if file.exists():

            file.unlink()
