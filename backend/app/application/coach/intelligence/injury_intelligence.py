from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    InjuryStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class InjuryIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding | None:

        if not context.injuries:

            return None

        return Finding(
            code=InjuryStatus.ACTIVE.value,
            severity=FindingSeverity.ATTENTION,
            params={
                "injuries": ", ".join(context.injuries),
            },
        )
