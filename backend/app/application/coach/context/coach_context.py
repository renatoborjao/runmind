from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)
from app.domain.entities.runner_profile import (
    RunnerProfile,
)


@dataclass(slots=True)
class CoachContext:

    # ==========================
    # Dados principais
    # ==========================

    runner: RunnerProfile

    planned: PlannedSession

    executed: EnrichedActivity

    # ==========================
    # Histórico
    # ==========================

    previous_trainings: list = field(
        default_factory=list,
    )

    weekly_volume: float = 0

    weekly_goal: float = 0

    consistency: float = 0

    # ==========================
    # Recuperação
    # ==========================

    fatigue: float = 0

    recovery_hours: int = 0

    # ==========================
    # Saúde
    # ==========================

    injuries: list[str] = field(
        default_factory=list,
    )