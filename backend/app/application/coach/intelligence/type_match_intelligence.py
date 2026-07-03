from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    TypeMatchStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class TypeMatchIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        planned_type = context.planned.workout_type.upper().replace(
            " ",
            "_",
        )

        executed_type = context.executed.training_type

        matches = (
            planned_type.startswith(executed_type)
            or executed_type.startswith(planned_type)
        )

        if matches:

            return Finding(
                code=TypeMatchStatus.MATCH.value,
                severity=FindingSeverity.POSITIVE,
                params={},
            )

        return Finding(
            code=TypeMatchStatus.MISMATCH.value,
            severity=FindingSeverity.ATTENTION,
            params={
                "planned_type": context.planned.workout_type,
                "executed_type": context.executed.training_type.lower(),
            },
        )
