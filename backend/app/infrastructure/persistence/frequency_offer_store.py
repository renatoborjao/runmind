"""Marca que o coach ofereceu ao atleta OFICIALIZAR um dia a mais (ele treina em
rotina além dos dias registrados). Assim, quando ele responder "SIM", sabemos
que o sim é sobre isso — e qual dia/quantos dias aplicar. Vale por uma janela
curta (some se ele não responder). Espelha o GarminOfferStore.
Ver [[project_reconciliacao_coach]]."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "reconcile" / "freq_offer"
)

# a oferta expira: um "sim" dias depois não deve remontar a semana sozinho
_TTL_SECONDS = 72 * 3600


class FrequencyOfferStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(profile: str, days: int, weekday: str) -> None:
        """Estagia a oferta: `days` (nº alvo de dias) e `weekday` (o dia extra a
        oficializar, nome em inglês)."""

        _STORAGE.mkdir(parents=True, exist_ok=True)

        FrequencyOfferStore._file(profile).write_text(
            json.dumps({"ts": time.time(), "days": days, "weekday": weekday}),
            encoding="utf-8",
        )

    @staticmethod
    def get_pending(profile: str) -> dict | None:
        """A oferta viva ({days, weekday}), ou None se não há / expirou."""

        file = FrequencyOfferStore._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return None

        if time.time() - float(data.get("ts", 0)) > _TTL_SECONDS:

            return None

        return data

    @staticmethod
    def clear(profile: str) -> None:

        FrequencyOfferStore._file(profile).unlink(missing_ok=True)
