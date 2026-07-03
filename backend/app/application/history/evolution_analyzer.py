from __future__ import annotations

from datetime import UTC, date, datetime

from app.application.history.weekly_buckets import (
    group_by_week,
    last_week_keys,
    week_start,
    week_stats,
)
from app.domain.entities.training_history import TrainingHistory

STABLE_THRESHOLD_PERCENT = 5


class EvolutionAnalyzer:
    """Série temporal semanal do corredor (volume, pace, FC) com
    tendência das 4 semanas mais recentes vs. as 4 anteriores."""

    @staticmethod
    def analyze(
        history: TrainingHistory,
        weeks: int = 12,
        reference_date: date | None = None,
    ) -> dict:

        reference_date = (
            reference_date or datetime.now(UTC).date()
        )

        buckets = group_by_week(history.activities)

        keys = last_week_keys(reference_date, weeks)

        series = [
            {
                "week_start": week_start(key).isoformat(),
                **week_stats(buckets.get(key, [])),
            }
            for key in keys
        ]

        return {
            "weeks": weeks,
            "series": series,
            "trends": {
                "volume": EvolutionAnalyzer._trend(
                    [week["distance_km"] for week in series],
                ),
                "pace": EvolutionAnalyzer._trend(
                    [week["avg_pace_min_km"] for week in series],
                ),
            },
        }

    @staticmethod
    def _trend(values: list) -> dict:

        recent = [
            value
            for value in values[-4:]
            if value
        ]

        previous = [
            value
            for value in values[-8:-4]
            if value
        ]

        if not recent or not previous:

            return {
                "delta_percent": None,
                "direction": "stable",
            }

        recent_avg = sum(recent) / len(recent)

        previous_avg = sum(previous) / len(previous)

        delta_percent = round(
            (recent_avg - previous_avg) / previous_avg * 100,
            1,
        )

        if delta_percent > STABLE_THRESHOLD_PERCENT:

            direction = "up"

        elif delta_percent < -STABLE_THRESHOLD_PERCENT:

            direction = "down"

        else:

            direction = "stable"

        return {
            "delta_percent": delta_percent,
            "direction": direction,
        }
