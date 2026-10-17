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
from app.domain.entities.workout_step import COOLDOWN, has_open_cooldown


class DistanceIntelligence:

    @staticmethod
    def process(
        context: CoachContext,
    ) -> Finding:

        planned_distance = context.planned.planned_distance_km or 0

        executed_distance = context.executed.activity.distance / 1000

        total_km = executed_distance

        # DESAQUECIMENTO ABERTO (o plano não fixou a distância dele): os km que o
        # atleta soltou no fim não são estouro de volume. Compara só até o bloco
        # principal; sem como separar o desaquecimento, não acusa "acima do plano".
        open_cooldown_km = None

        if has_open_cooldown(getattr(context.planned, "steps", None) or []):

            open_cooldown_km = DistanceIntelligence._open_cooldown_km(
                context.block_comparison
            )

            if open_cooldown_km is not None:

                executed_distance -= open_cooldown_km

            elif executed_distance > planned_distance:

                executed_distance = planned_distance

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
                "executed_km": round(total_km, 1),
                **(
                    {"open_cooldown_km": round(open_cooldown_km, 1)}
                    if open_cooldown_km is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _open_cooldown_km(comparison) -> float | None:
        """Km que o atleta fez no desaquecimento LIVRE (bloco COOLDOWN sem
        distância/duração prescrita) pelas voltas pareadas. None sem comparação."""

        if comparison is None:

            return None

        meters = [
            block.executed_distance_m
            for block in comparison.blocks
            if block.kind == COOLDOWN
            and not block.planned_distance_m
            and not block.planned_duration_sec
        ]

        return sum(meters) / 1000 if meters else None
