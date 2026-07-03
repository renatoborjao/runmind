from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    PaceEffortLevel,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class PerformanceIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        pace = context.executed.pace_min_km

        if pace <= 4.30:

            code = PaceEffortLevel.VERY_FAST

        elif pace <= 5.20:

            code = PaceEffortLevel.FAST

        elif pace <= 6.20:

            code = PaceEffortLevel.MODERATE

        else:

            code = PaceEffortLevel.EASY

        return Finding(
            code=code.value,
            severity=FindingSeverity.NEUTRAL,
            params={
                "pace_min_km": pace,
            },
        )
