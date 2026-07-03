from app.domain.entities.training_history import TrainingHistory


class HistoryIntelligence:

    @staticmethod
    def analyze(history: TrainingHistory) -> dict:

        activities = history.activities

        if not activities:
            return {
                "weekly_volume": 0,
                "longest_run": 0,
                "average_distance": 0,
                "average_pace": 0,
                "average_hr": 0,
            }

        total_distance = sum(a.distance for a in activities) / 1000

        total_time = sum(a.moving_time for a in activities)

        average_distance = total_distance / len(activities)

        longest_run = max(a.distance for a in activities) / 1000

        average_hr = history.average_hr or 0

        average_pace = total_time / (total_distance * 60)

        return {
            "weekly_volume": round(total_distance / 5, 1),
            "longest_run": round(longest_run, 1),
            "average_distance": round(average_distance, 1),
            "average_pace": round(average_pace, 2),
            "average_hr": average_hr,
        }