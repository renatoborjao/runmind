from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NextTraining:

    day: str

    workout_type: str

    objective: str

    distance_km: float

    pace: str

    heart_rate: str

    warmup: str

    main_set: str

    cooldown: str

    shoes: str

    notes: str