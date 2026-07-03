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

    intensity: Finding

    pace_effort: Finding

    recovery: Finding

    # None quando o treino foi em dia sem sessão planejada
    distance: Finding | None = None

    type_match: Finding | None = None

    unplanned: Finding | None = None

    fatigue: Finding | None = None

    consistency: Finding | None = None

    weekly_volume: Finding | None = None

    injury_risk: Finding | None = None

    next_training: NextTraining | None = None
