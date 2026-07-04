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

    # None = treino feito em dia sem sessão planejada (treino extra)
    planned: PlannedSession | None

    executed: EnrichedActivity

    # próxima sessão futura do plano (para o "🎯 Próximo treino")
    next_planned: PlannedSession | None = None

    # ==========================
    # Histórico
    # ==========================

    previous_trainings: list = field(
        default_factory=list,
    )

    weekly_volume: float = 0

    weekly_goal: float = 0

    consistency: float = 0

    # semanas completas que o cálculo de consistência avaliou — poucas
    # semanas = cedo demais para chamar a rotina de "irregular"
    history_weeks: int = 0

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