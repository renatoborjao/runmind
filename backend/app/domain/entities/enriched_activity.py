from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.activity import Activity
from app.domain.entities.workout_structure import WorkoutStructure
from app.domain.value_objects.hr_zones import HrZones


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

    # estrutura interna (splits/voltas); None quando não há detalhe
    structure: WorkoutStructure | None = None

    # régua de zonas de FC do atleta usada no rótulo (relógio/reserva de FC)
    hr_zones: HrZones | None = None
