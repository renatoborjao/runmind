from __future__ import annotations

from dataclasses import dataclass

from app.application.coach.models.next_training import (
    NextTraining,
)
from app.application.coach.signals.finding import (
    Finding,
)


@dataclass(slots=True)
class CoachAnalysis:

    distance: Finding

    type_match: Finding

    intensity: Finding

    pace_effort: Finding

    recovery: Finding

    fatigue: Finding | None = None

    consistency: Finding | None = None

    weekly_volume: Finding | None = None

    injury_risk: Finding | None = None

    next_training: NextTraining | None = None
