from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.signals.codes import (
    ConsistencyLevel,
    WeeklyVolumeStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


# Abaixo disso, ainda não há semanas completas suficientes para chamar a
# rotina de "irregular" sem injustiça (estreante, retorno recente).
MIN_WEEKS_TO_JUDGE_CONSISTENCY = 3


class HistoryIntelligence:

    @staticmethod
    def process_consistency(
        context: CoachContext,
    ) -> Finding:

        # Rotina baixa com histórico curto vira incentivo, não alerta:
        # cedo demais para julgar a regularidade.
        if (
            context.consistency < 50
            and context.history_weeks < MIN_WEEKS_TO_JUDGE_CONSISTENCY
        ):

            return Finding(
                code=ConsistencyLevel.BUILDING.value,
                severity=FindingSeverity.NEUTRAL,
                params={
                    "consistency": context.consistency,
                },
            )

        if context.consistency >= 90:

            code = ConsistencyLevel.EXCELLENT

            severity = FindingSeverity.POSITIVE

        elif context.consistency >= 75:

            code = ConsistencyLevel.GOOD

            severity = FindingSeverity.POSITIVE

        elif context.consistency >= 50:

            code = ConsistencyLevel.FAIR

            severity = FindingSeverity.NEUTRAL

        else:

            code = ConsistencyLevel.LOW

            severity = FindingSeverity.ATTENTION

        return Finding(
            code=code.value,
            severity=severity,
            params={
                "consistency": context.consistency,
            },
        )

    @staticmethod
    def process_weekly_volume(
        context: CoachContext,
    ) -> Finding:

        if context.weekly_goal <= 0:

            return Finding(
                code=WeeklyVolumeStatus.NO_GOAL.value,
                severity=FindingSeverity.NEUTRAL,
                params={},
            )

        progress = (
            context.weekly_volume / context.weekly_goal
        ) * 100

        if progress >= 100:

            code = WeeklyVolumeStatus.COMPLETED

        elif progress >= 80:

            code = WeeklyVolumeStatus.NEAR_COMPLETE

        else:

            code = WeeklyVolumeStatus.IN_PROGRESS

        return Finding(
            code=code.value,
            severity=FindingSeverity.POSITIVE,
            params={
                "progress_percent": round(progress, 1),
            },
        )
