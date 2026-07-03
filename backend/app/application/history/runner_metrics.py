from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_history import TrainingHistory


class RunnerMetricsBuilder:

    @staticmethod
    def build(
        history: TrainingHistory,
    ) -> RunnerMetrics:

        activities = history.activities

        paces = []

        for activity in activities:

            if activity.average_speed <= 0:
                continue

            pace = (
                (1000 / activity.average_speed)
                / 60
            )

            paces.append(pace)

        if not paces:
            raise Exception(
                "Histórico insuficiente."
            )

        average_pace = sum(paces) / len(paces)

        weekly = WeeklyVolumeAnalyzer.analyze(
            history
        )

        return RunnerMetrics(

            easy_pace_min=round(
                average_pace - 0.25,
                2,
            ),

            easy_pace_max=round(
                average_pace + 0.35,
                2,
            ),

            threshold_pace=round(
                average_pace - 0.60,
                2,
            ),

            vo2_pace=round(
                average_pace - 1.10,
                2,
            ),

            average_hr=history.average_hr or 0,

            max_long_run=round(
                history.longest_run.distance / 1000,
                1,
            ),

            weekly_volume=weekly[
                "average_4_weeks"
            ],

            consistency=95,
        )