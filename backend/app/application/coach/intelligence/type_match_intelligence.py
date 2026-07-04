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
    LONG_RUN_LABEL_MIN_KM,
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

        compatible = set(_COMPATIBLE.get(planned_type, set()))

        # Longão só é longão a partir de 10km. Abaixo disso o objetivo é,
        # na prática, base aeróbica: uma rodagem leve/regenerativa
        # executada não é desvio do plano — não faz sentido cobrar o
        # "longão" de um treino planejado de 9km.
        if (
            planned_type == "LONG_RUN"
            and (context.planned.planned_distance_km or 0)
            < LONG_RUN_LABEL_MIN_KM
        ):

            compatible |= {"EASY", "RECOVERY"}

        matches = (
            planned_type == executed_type
            or executed_type in compatible
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
