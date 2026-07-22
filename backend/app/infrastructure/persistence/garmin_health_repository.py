import json
from pathlib import Path

from app.domain.entities.daily_health import DailyHealth

_STORAGE = (
    Path(__file__)
    .resolve()
    .parents[3]
    / "storage"
    / "garmin_health"
)


class GarminHealthRepository:
    """Histórico permanente dos retratos diários de saúde do Garmin, por
    atleta — a SÉRIE ao longo dos dias é o que dá valor pra análise de
    carga/prontidão depois.

    storage/garmin_health/{profile}.json — lista de snapshots, um por dia,
    ordenada por data. Upsert por data (re-puxar o mesmo dia sobrescreve, não
    duplica)."""

    def __init__(self):

        _STORAGE.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    def load(self, profile: str) -> list[DailyHealth]:

        file = self._file(profile)

        if not file.exists():

            return []

        with open(file, encoding="utf-8") as f:

            raw = json.load(f)

        return [DailyHealth.from_dict(item) for item in raw]

    def has_date(self, profile: str, day: str) -> bool:

        return any(h.date == day for h in self.load(profile))

    def latest(self, profile: str) -> DailyHealth | None:

        snapshots = self.load(profile)

        return snapshots[-1] if snapshots else None

    def upsert(self, profile: str, health: DailyHealth) -> None:
        """Grava o snapshot do dia; se já existia um pra a mesma data,
        substitui. Mantém a lista ordenada por data."""

        by_date = {h.date: h for h in self.load(profile)}

        by_date[health.date] = health

        ordered = [by_date[d] for d in sorted(by_date)]

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(
                [h.to_dict() for h in ordered],
                f,
                ensure_ascii=False,
                indent=2,
            )
