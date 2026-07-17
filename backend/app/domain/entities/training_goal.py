from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class TrainingGoal:

    name: str

    distance_km: float

    target_time: str | None

    # None = atleta sem prova alvo (progressão contínua)
    race_date: date | None

    priority: str = "A"