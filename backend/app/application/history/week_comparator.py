from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.application.history.weekly_buckets import (
    group_by_week,
    week_start,
    week_stats,
)
from app.domain.entities.training_history import TrainingHistory


class WeekComparator:
    """Compara a semana ISO atual com a anterior (calendário):
    semana sem treino conta como zero, não é pulada."""

    @staticmethod
    def compare(
        history: TrainingHistory,
        reference_date: date | None = None,
    ) -> dict:

        reference_date = (
            reference_date or datetime.now(UTC).date()
        )

        buckets = group_by_week(history.activities)

        current_key = reference_date.isocalendar()[:2]

        previous_key = (
            reference_date - timedelta(weeks=1)
        ).isocalendar()[:2]

        current = week_stats(buckets.get(current_key, []))

        previous = week_stats(buckets.get(previous_key, []))

        return {
            "current_week": {
                "week_start": week_start(current_key).isoformat(),
                **current,
            },
            "previous_week": {
                "week_start": week_start(previous_key).isoformat(),
                **previous,
            },
            "delta": WeekComparator._delta(current, previous),
        }

    @staticmethod
    def _delta(current: dict, previous: dict) -> dict:

        volume_delta_percent = (
            round(
                (current["distance_km"] - previous["distance_km"])
                / previous["distance_km"]
                * 100,
                1,
            )
            if previous["distance_km"] > 0
            else None
        )

        return {
            "distance_km": round(
                current["distance_km"] - previous["distance_km"],
                1,
            ),
            "runs": current["runs"] - previous["runs"],
            "avg_pace_min_km": WeekComparator._optional_delta(
                current["avg_pace_min_km"],
                previous["avg_pace_min_km"],
            ),
            "avg_hr": WeekComparator._optional_delta(
                current["avg_hr"],
                previous["avg_hr"],
            ),
            "volume_delta_percent": volume_delta_percent,
        }

    @staticmethod
    def _optional_delta(
        current: float | None,
        previous: float | None,
    ) -> float | None:

        if current is None or previous is None:

            return None

        return round(current - previous, 2)
