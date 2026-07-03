from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.models.next_training import (
    NextTraining,
)


class PlanningIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> NextTraining:

        planned = context.planned

        return NextTraining(
            day=planned.day,
            workout_type=planned.workout_type,
            objective=planned.objective,
            distance_km=planned.planned_distance_km or 0,
            pace=PlanningIntelligence._format_pace(planned),
            heart_rate="-",
            warmup="-",
            main_set="-",
            cooldown="-",
            shoes="-",
            notes=planned.notes or "-",
        )

    @staticmethod
    def _format_pace(
        planned,
    ) -> str:

        if planned.target_pace_min and planned.target_pace_max:

            return (
                f"{planned.target_pace_min} - "
                f"{planned.target_pace_max}"
            )

        return "-"
