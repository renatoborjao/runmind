from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    DistanceStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class DistanceIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        planned_distance = context.planned.planned_distance_km or 0

        executed_distance = context.executed.activity.distance / 1000

        if planned_distance == 0:

            return Finding(
                code=DistanceStatus.UNKNOWN.value,
                severity=FindingSeverity.NEUTRAL,
                params={
                    "planned_km": planned_distance,
                    "executed_km": round(executed_distance, 1),
                },
            )

        delta_percent = round(
            (
                (executed_distance - planned_distance)
                / planned_distance
            )
            * 100,
            1,
        )

        if delta_percent > 10:

            code = DistanceStatus.ABOVE

            severity = FindingSeverity.ATTENTION

        elif delta_percent < -10:

            code = DistanceStatus.BELOW

            severity = FindingSeverity.ATTENTION

        else:

            code = DistanceStatus.OK

            severity = FindingSeverity.POSITIVE

        return Finding(
            code=code.value,
            severity=severity,
            params={
                "delta_percent": delta_percent,
                "delta_percent_abs": abs(delta_percent),
                "planned_km": planned_distance,
                "executed_km": round(executed_distance, 1),
            },
        )
