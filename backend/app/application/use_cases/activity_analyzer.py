from app.application.services.activity_insight_engine import ActivityInsightEngine
from app.application.services.report_builder import ReportBuilder
from app.application.services.statistics_engine import StatisticsEngine
from app.application.services.training_comparator import TrainingComparator
from app.domain.entities.training_history import TrainingHistory
from app.presentation.schemas.mappers import to_activity_response


class ActivityAnalyzer:

    @staticmethod
    def execute(history: TrainingHistory):

        summary = StatisticsEngine.build(
            history.activities
        )

        comparison = None

        if history.previous:

            comparison = TrainingComparator.compare(
                history.latest,
                history.previous,
            )

        coach = ActivityInsightEngine.analyze(
            history.latest
        )

        report = ReportBuilder.build(
            history,
            summary,
            comparison,
            coach,
        )

        report["activities"] = [
            to_activity_response(activity)
            for activity in history.activities
        ]

        return report