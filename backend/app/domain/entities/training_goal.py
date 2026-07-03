from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class TrainingGoal:

    name: str

    distance_km: float

    target_time: str

    race_date: date

    priority: str = "A"