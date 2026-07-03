from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    IntensityLevel,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class IntensityIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        intensity = context.executed.intensity

        if intensity == "VERY_HIGH":

            code = IntensityLevel.VERY_HIGH

            severity = FindingSeverity.ATTENTION

        elif intensity == "HIGH":

            code = IntensityLevel.HIGH

            severity = FindingSeverity.POSITIVE

        elif intensity == "MEDIUM":

            code = IntensityLevel.MEDIUM

            severity = FindingSeverity.POSITIVE

        else:

            code = IntensityLevel.LOW

            severity = FindingSeverity.POSITIVE

        return Finding(
            code=code.value,
            severity=severity,
            params={
                "intensity": intensity,
            },
        )
