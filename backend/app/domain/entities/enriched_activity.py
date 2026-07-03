from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.activity import Activity


@dataclass(slots=True)
class EnrichedActivity:

    activity: Activity

    pace_min_km: float

    training_type: str

    intensity: str

    estimated_zone: str

    training_load: float

    fatigue_score: float

    recovery_hours: int

    efficiency_score: float

    indoor: bool