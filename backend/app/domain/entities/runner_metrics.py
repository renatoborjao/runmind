from __future__ import annotations

from dataclasses import dataclass

from app.domain.value_objects.hr_zones import HrZones


@dataclass(slots=True)
class RunnerMetrics:

    easy_pace_min: float

    easy_pace_max: float

    threshold_pace: float

    vo2_pace: float

    average_hr: float

    max_long_run: float

    weekly_volume: float

    # régua de zonas de FC do atleta (relógio / reserva de FC / %FCmáx). None
    # = sem como saber (sem idade nem FC máx) — aí ninguém rotula zona.
    hr_zones: HrZones | None = None
