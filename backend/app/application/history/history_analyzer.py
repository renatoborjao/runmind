from collections import Counter

from app.application.history.training_classifier import (
    TrainingClassifier,
)
from app.domain.entities.training_history import TrainingHistory


class HistoryAnalyzer:

    @staticmethod
    def analyze(
        history: TrainingHistory,
    ) -> dict:

        total_distance = history.total_distance / 1000

        total_runs = history.total_runs

        average_distance = (
            total_distance / total_runs
            if total_runs
            else 0
        )

        longest_run = 0

        if history.longest_run:
            longest_run = (
                history.longest_run.distance / 1000
            )

        average_hr = history.average_hr

        training_types = Counter()

        for activity in history.activities:

            training_type = (
                TrainingClassifier.classify(
                    activity
                )
            )

            training_types[training_type] += 1

        return {

            "total_runs": total_runs,

            "total_distance": round(
                total_distance,
                1,
            ),

            "average_distance": round(
                average_distance,
                1,
            ),

            "longest_run": round(
                longest_run,
                1,
            ),

            "average_hr": average_hr,

            "training_types": dict(
                training_types
            ),
        }