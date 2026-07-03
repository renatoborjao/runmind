from app.domain.entities.training_assessment import TrainingAssessment


class TrainingStrategy:

    @staticmethod
    def build(
        assessment: TrainingAssessment,
    ) -> dict:

        weekly_volume = assessment.recommended_weekly_volume

        longest_run = min(
            assessment.longest_run,
            round(weekly_volume * 0.35, 1),
        )

        remaining = weekly_volume - longest_run

        easy_run = round(remaining * 0.45, 1)

        quality_run = round(remaining * 0.55, 1)

        return {

            "week_type": "BUILD",

            "weekly_volume": weekly_volume,

            "long_run": longest_run,

            "easy_run": easy_run,

            "quality_run": quality_run,

            "quality_type": "VO2",
        }