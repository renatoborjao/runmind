from app.domain.entities.training_assessment import TrainingAssessment


class LoadEngine:

    @staticmethod
    def execute(
        assessment: TrainingAssessment,
    ) -> float:

        return assessment.current_weekly_volume