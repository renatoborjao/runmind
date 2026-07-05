from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlannedSession:

    day: str

    workout_type: str

    objective: str

    planned_distance_km: float | None

    planned_duration_minutes: int | None

    target_pace_min: str | None

    target_pace_max: str | None

    notes: str = ""

    adjusted: bool = False

    adjustment_reason: str | None = None

    # Estrutura de intervalos para run/walk (caminhada/trote). Quando
    # presente, a sessão é medida em tempo, não em km. Ex:
    #   {"warmup_min": 5, "trot_sec": 60, "walk_sec": 180,
    #    "reps": 6, "cooldown_min": 5}
    intervals: dict | None = None