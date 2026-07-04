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
from app.application.coach.writer.labels import (
    plan_workout_label,
    workout_type_label,
)

# Um progressivo executado costuma ser classificado como rodagem/tempo —
# não é desvio do plano.
_COMPATIBLE = {
    "PROGRESSION": {"EASY", "TEMPO", "VO2"},
}


class TypeMatchIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        planned_type = context.planned.workout_type

        executed_type = context.executed.training_type

        matches = (
            planned_type == executed_type
            or executed_type in _COMPATIBLE.get(planned_type, set())
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
                "planned_type": plan_workout_label(
                    planned_type,
                    context.planned.planned_distance_km,
                ),
                # minúsculo: entra no meio da frase do phrasebook
                "executed_type": workout_type_label(
                    executed_type,
                ).lower(),
            },
        )
