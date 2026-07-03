from __future__ import annotations

from dataclasses import dataclass, field

from app.application.coach.models.next_training import (
    NextTraining,
)
from app.application.coach.signals.finding import (
    Finding,
)


@dataclass(slots=True)
class CoachSummary:

    runner_name: str

    positives: list[Finding] = field(
        default_factory=list,
    )

    improvements: list[Finding] = field(
        default_factory=list,
    )

    history: list[Finding] = field(
        default_factory=list,
    )

    recovery: list[Finding] = field(
        default_factory=list,
    )

    next_training: NextTraining | None = None
