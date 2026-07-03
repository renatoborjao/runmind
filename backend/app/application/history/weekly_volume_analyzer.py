from app.application.history.weekly_buckets import group_by_week
from app.domain.entities.training_history import TrainingHistory


class WeeklyVolumeAnalyzer:

    @staticmethod
    def analyze(history: TrainingHistory) -> dict:

        buckets = group_by_week(history.activities)

        if not buckets:
            return {
                "last_week": 0,
                "average_4_weeks": 0,
                "max_week": 0,
            }

        # ordem cronológica (chave ISO ordena naturalmente)
        volumes = [
            sum(
                activity.distance for activity in buckets[key]
            ) / 1000
            for key in sorted(buckets)
        ]

        last_week = volumes[-1]

        last_4_weeks = volumes[-4:]

        average_4_weeks = sum(last_4_weeks) / len(last_4_weeks)

        return {
            "last_week": round(last_week, 1),
            "average_4_weeks": round(average_4_weeks, 1),
            "max_week": round(max(volumes), 1),
        }
