"""Guarda os treinos de FORA do Ritmind que o coach acabou de apontar no
relógio do atleta (ver `find_foreign_scheduled`), esperando o OK dele pra
apagar ("pode apagar"). Nunca apagamos treino que não é nosso sem esse OK —
pode ser do atleta, do Garmin ou de outro app. Vale por uma janela curta."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "garmin" / "foreign"
)

_TTL_SECONDS = 48 * 3600


class ForeignWorkoutStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(profile: str, items: list[dict]) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        ForeignWorkoutStore._file(profile).write_text(
            json.dumps({"ts": time.time(), "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def pending(profile: str) -> list[dict]:
        """Treinos apontados e ainda não resolvidos (dentro do TTL), ou []."""

        file = ForeignWorkoutStore._file(profile)

        if not file.exists():

            return []

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            if (time.time() - data["ts"]) >= _TTL_SECONDS:

                return []

            return list(data.get("items") or [])

        except (json.JSONDecodeError, KeyError, OSError, TypeError):

            return []

    @staticmethod
    def clear(profile: str) -> None:

        file = ForeignWorkoutStore._file(profile)

        if file.exists():

            file.unlink()
