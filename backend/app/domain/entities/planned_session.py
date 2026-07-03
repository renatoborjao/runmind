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