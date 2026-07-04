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
from app.application.coach.writer.phrasebook import (
    RECOVERY_WHEN_NEXT,
    RECOVERY_WHEN_WEEK_DONE,
)
from app.core.weekdays import weekday_label


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

        # Sem próxima sessão no plano = semana concluída; o texto de
        # recuperação/fechamento não pode falar em "amanhã" nesse caso.
        next_day = (
            weekday_label(context.next_planned.day)
            if context.next_planned is not None
            else None
        )

        when = (
            RECOVERY_WHEN_NEXT.format(next_day=next_day)
            if next_day is not None
            else RECOVERY_WHEN_WEEK_DONE
        )

        return Finding(
            code=code.value,
            severity=severity,
            params={
                "recovery_hours": context.recovery_hours,
                "when": when,
                "next_day": next_day,
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
