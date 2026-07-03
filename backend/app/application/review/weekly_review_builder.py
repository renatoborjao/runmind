from __future__ import annotations

from datetime import date

from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.application.history.evolution_analyzer import EvolutionAnalyzer
from app.application.history.week_comparator import WeekComparator
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory

TREND_WEEKS = 8


class WeeklyReviewBuilder:
    """Monta os dados do resumo semanal (semana que está fechando)."""

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
        reference_date: date | None = None,
    ) -> dict:

        reference_date = reference_date or today_local()

        comparison = WeekComparator.compare(
            history,
            reference_date=reference_date,
        )

        evolution = EvolutionAnalyzer.analyze(
            history,
            weeks=TREND_WEEKS,
            reference_date=reference_date,
        )

        consistency = ConsistencyCalculator.calculate(
            history,
            runner.weekly_training_days,
            reference_date=reference_date,
        )

        return {
            "week_start": comparison["current_week"]["week_start"],
            "comparison": comparison,
            "trends": evolution["trends"],
            "consistency": consistency,
        }
