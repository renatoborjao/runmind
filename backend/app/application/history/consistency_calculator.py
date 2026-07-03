from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from app.domain.entities.training_history import TrainingHistory


class ConsistencyCalculator:
    """Adesão ao plano: média de dias treinados vs. dias planejados
    por semana, nas últimas `weeks` semanas."""

    @staticmethod
    def calculate(
        history: TrainingHistory,
        weekly_training_days: int,
        weeks: int = 4,
        reference_date: date | None = None,
    ) -> float:

        if weekly_training_days <= 0:

            return 0.0

        reference_date = reference_date or datetime.now(UTC).date()

        days_by_week: dict[tuple[int, int], set[date]] = defaultdict(set)

        for activity in history.activities:

            activity_date = activity.start_date.date()

            week_key = activity_date.isocalendar()[:2]

            days_by_week[week_key].add(activity_date)

        week_keys = [
            (reference_date - timedelta(weeks=i)).isocalendar()[:2]
            for i in range(weeks)
        ]

        adherence_scores = [
            min(
                len(days_by_week.get(week_key, set()))
                / weekly_training_days,
                1.0,
            )
            for week_key in week_keys
        ]

        return round(
            sum(adherence_scores) / len(adherence_scores) * 100,
            1,
        )
