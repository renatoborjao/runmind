from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)
from app.domain.entities.runner_profile import (
    RunnerProfile,
)
from app.domain.entities.training_assessment import (
    TrainingAssessment,
)
from app.domain.entities.training_history import (
    TrainingHistory,
)


class CoachContextBuilder:

    @staticmethod
    def build(
        runner: RunnerProfile,
        planned: PlannedSession | None,
        executed: EnrichedActivity,
        history: TrainingHistory,
        assessment: TrainingAssessment,
        next_planned: PlannedSession | None = None,
    ) -> CoachContext:

        return CoachContext(

            runner=runner,

            planned=planned,

            executed=executed,

            next_planned=next_planned,

            fatigue=executed.fatigue_score,

            recovery_hours=executed.recovery_hours,

            previous_trainings=CoachContextBuilder._previous_trainings(
                history,
            ),

            weekly_volume=assessment.current_weekly_volume,

            weekly_goal=assessment.recommended_weekly_volume,

            consistency=assessment.consistency,

            history_weeks=ConsistencyCalculator.evaluated_weeks(
                history,
            ),

            injuries=runner.injuries,

        )

    @staticmethod
    def _previous_trainings(
        history: TrainingHistory,
    ) -> list:

        if len(history.activities) <= 1:

            return []

        return history.activities[1:]
