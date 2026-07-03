from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    FatigueLevel,
    RecoveryStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class RecoveryIntelligence:

    @staticmethod
    def process_recovery(
        context: CoachContext,
    ) -> Finding:

        if context.recovery_hours >= 48:

            code = RecoveryStatus.LONG

            severity = FindingSeverity.ATTENTION

        elif context.recovery_hours >= 36:

            code = RecoveryStatus.MODERATE

            severity = FindingSeverity.NEUTRAL

        else:

            code = RecoveryStatus.SHORT

            severity = FindingSeverity.POSITIVE

        return Finding(
            code=code.value,
            severity=severity,
            params={
                "recovery_hours": context.recovery_hours,
            },
        )

    @staticmethod
    def process_fatigue(
        context: CoachContext,
    ) -> Finding | None:

        if context.fatigue >= 80:

            code = FatigueLevel.HIGH

        elif context.fatigue >= 50:

            code = FatigueLevel.MODERATE

        else:

            return None

        return Finding(
            code=code.value,
            severity=FindingSeverity.ATTENTION,
            params={
                "fatigue": context.fatigue,
            },
        )
