from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.intelligence.distance_intelligence import (
    DistanceIntelligence,
)
from app.application.coach.intelligence.history_intelligence import (
    HistoryIntelligence,
)
from app.application.coach.intelligence.injury_intelligence import (
    InjuryIntelligence,
)
from app.application.coach.intelligence.intensity_intelligence import (
    IntensityIntelligence,
)
from app.application.coach.intelligence.performance_intelligence import (
    PerformanceIntelligence,
)
from app.application.coach.intelligence.planning_intelligence import (
    PlanningIntelligence,
)
from app.application.coach.intelligence.recovery_intelligence import (
    RecoveryIntelligence,
)
from app.application.coach.intelligence.type_match_intelligence import (
    TypeMatchIntelligence,
)
from app.application.coach.signals.coach_analysis import (
    CoachAnalysis,
)
from app.application.coach.signals.codes import (
    WorkoutPlanStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)


class CoachPipeline:

    @staticmethod
    def execute(
        context: CoachContext,
    ) -> CoachAnalysis:

        # Treino em dia sem sessão planejada: não há o que comparar
        # com o plano — registra como treino extra.
        if context.planned is None:

            distance = None

            type_match = None

            unplanned = Finding(
                code=WorkoutPlanStatus.UNPLANNED.value,
                severity=FindingSeverity.NEUTRAL,
                params={},
            )

        else:

            distance = DistanceIntelligence.process(context)

            type_match = TypeMatchIntelligence.process(context)

            unplanned = None

        return CoachAnalysis(
            distance=distance,
            type_match=type_match,
            unplanned=unplanned,
            intensity=IntensityIntelligence.process(context),
            pace_effort=PerformanceIntelligence.process(context),
            recovery=RecoveryIntelligence.process_recovery(context),
            fatigue=RecoveryIntelligence.process_fatigue(context),
            consistency=HistoryIntelligence.process_consistency(context),
            weekly_volume=HistoryIntelligence.process_weekly_volume(context),
            injury_risk=InjuryIntelligence.process(context),
            next_training=PlanningIntelligence.process(context),
        )
