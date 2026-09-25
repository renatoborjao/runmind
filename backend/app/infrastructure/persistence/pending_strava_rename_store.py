"""Renomeações do Strava que ficaram PENDENTES porque a cópia da corrida ainda
não tinha chegado no Strava na hora da análise (atleta com Garmin é analisado
pelo Garmin, que é upstream do Strava — a cópia sincroniza minutos/horas
depois). O nome já decidido fica guardado aqui e é aplicado quando a cópia
aparece (webhook do Strava ou varredura periódica). Expira em 24h.
Ver [[project_strava_rename]]."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "pending_strava_rename"
)

# depois disso desiste: a cópia não veio (atleta sem sync Garmin→Strava)
MAX_AGE_SECONDS = 24 * 3600


class PendingStravaRenameStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def items(profile: str) -> list[dict]:

        file = PendingStravaRenameStore._file(profile)

        if not file.exists():

            return []

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError):

            return []

        return data if isinstance(data, list) else []

    @staticmethod
    def profiles() -> list[str]:

        if not _STORAGE.exists():

            return []

        return sorted(f.stem for f in _STORAGE.glob("*.json"))

    @staticmethod
    def add(
        profile: str,
        activity_id,
        start_ts: float,
        distance_m: float,
        name: str,
    ) -> None:
        """Guarda (ou atualiza) a pendência desta corrida. Idempotente por
        activity_id — reanálise do mesmo treino não duplica."""

        items = [
            i for i in PendingStravaRenameStore.items(profile)
            if str(i.get("activity_id")) != str(activity_id)
        ]

        items.append({
            "activity_id": str(activity_id),
            "start_ts": start_ts,
            "distance_m": distance_m,
            "name": name,
            "created_at": time.time(),
        })

        PendingStravaRenameStore._save(profile, items)

    @staticmethod
    def remove(profile: str, activity_id) -> None:

        items = [
            i for i in PendingStravaRenameStore.items(profile)
            if str(i.get("activity_id")) != str(activity_id)
        ]

        PendingStravaRenameStore._save(profile, items)

    @staticmethod
    def _save(profile: str, items: list[dict]) -> None:

        file = PendingStravaRenameStore._file(profile)

        if not items:

            file.unlink(missing_ok=True)

            return

        _STORAGE.mkdir(parents=True, exist_ok=True)

        file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
