"""Marca que oferecemos ao atleta mandar os treinos pro Garmin (na entrega
do plano ou numa mudança mid-week). Assim, quando ele responder "SIM", sabemos
que o sim é sobre o Garmin — e não uma afirmação solta. Vale por uma janela
curta (a oferta é do plano recém-enviado).

Guarda também se JÁ mandamos o lembrete desta oferta — pra o coach cobrar UMA
vez o atleta que pediu a mudança e nunca confirmou o envio pro relógio (a
mudança ficaria perdida no relógio até a oferta expirar). Ver
[[WatchUpdateReminderNotifier]]."""

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
            json.dumps({"ts": time.time(), "reminded": False}),
            encoding="utf-8",
        )

    @staticmethod
    def _read(profile: str) -> dict | None:
        """Payload da oferta se ainda VÁLIDA (dentro do TTL), senão None.
        Tolera o formato legado {"ts": ...} (sem 'reminded')."""

        file = GarminOfferStore._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            ts = data["ts"]

        except (json.JSONDecodeError, KeyError, OSError, TypeError):

            return None

        if (time.time() - ts) >= _TTL_SECONDS:

            return None

        return data

    @staticmethod
    def is_pending(profile: str) -> bool:

        return GarminOfferStore._read(profile) is not None

    @staticmethod
    def reminder_due(profile: str, min_age_seconds: float) -> bool:
        """Há oferta pendente, com idade >= min_age (o atleta teve tempo de
        responder no fluxo natural) e que AINDA não foi lembrada. É o sinal de
        'pediu a mudança e não confirmou o envio pro relógio'."""

        data = GarminOfferStore._read(profile)

        if data is None:

            return False

        if data.get("reminded"):

            return False

        return (time.time() - data["ts"]) >= min_age_seconds

    @staticmethod
    def mark_reminded(profile: str) -> None:
        """Marca que o lembrete desta oferta já saiu — UM por episódio
        (orientar-não-repetir). Preserva o ts (a oferta segue válida pro 'sim')."""

        data = GarminOfferStore._read(profile)

        if data is None:

            return

        data["reminded"] = True

        GarminOfferStore._file(profile).write_text(
            json.dumps(data),
            encoding="utf-8",
        )

    @staticmethod
    def clear(profile: str) -> None:

        file = GarminOfferStore._file(profile)

        if file.exists():

            file.unlink()
