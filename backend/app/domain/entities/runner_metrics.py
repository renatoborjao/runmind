from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunnerMetrics:

    easy_pace_min: float

    easy_pace_max: float

    threshold_pace: float

    vo2_pace: float

    average_hr: float

    max_long_run: float

    weekly_volume: float

    consistency: float