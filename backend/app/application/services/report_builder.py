from app.domain.entities.training_history import TrainingHistory


class ReportBuilder:

    @staticmethod
    def build(history, summary, comparison, coach):

        latest = history.latest

        return {
            "training": {
                "title": latest.name,
                "distance_km": round(latest.distance / 1000, 2),
                "duration_minutes": round(latest.elapsed_time / 60, 1),
                "pace": summary["average_pace"],
                "average_hr": latest.average_heartrate,
            },

            "summary": summary,

            "comparison": comparison,

            "coach": coach,
        }