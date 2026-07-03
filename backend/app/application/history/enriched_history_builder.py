from app.application.history.activity_enricher import ActivityEnricher
from app.application.history.runner_metrics import RunnerMetricsBuilder
from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.training_history import TrainingHistory


class EnrichedHistoryBuilder:

    @staticmethod
    def build(
        history: TrainingHistory,
    ) -> list[EnrichedActivity]:

        metrics = RunnerMetricsBuilder.build(
            history
        )

        return [
            ActivityEnricher.enrich(
                activity,
                metrics,
            )
            for activity in history.activities
        ]