from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.application.history.planned_execution_matcher import (
    PlannedExecutionMatcher,
)
from app.application.history.weekly_buckets import activity_date
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)
from app.domain.entities.runner_profile import (
    RunnerProfile,
)
from app.domain.entities.training_assessment import (
    TrainingAssessment,
)
from app.domain.entities.training_history import (
    TrainingHistory,
)


class CoachContextBuilder:

    @staticmethod
    def build(
        runner: RunnerProfile,
        planned: PlannedSession | None,
        executed: EnrichedActivity,
        history: TrainingHistory,
        assessment: TrainingAssessment,
        next_planned: PlannedSession | None = None,
        planned_date=None,
        next_planned_date=None,
        plan_weekly_volume: float = 0.0,
    ) -> CoachContext:

        return CoachContext(

            runner=runner,

            planned=planned,

            executed=executed,

            planned_date=planned_date,

            next_planned=next_planned,

            next_planned_date=next_planned_date,

            block_comparison=(
                PlannedExecutionMatcher.match(planned, executed.activity)
                if planned is not None
                else None
            ),

            fatigue=executed.fatigue_score,

            recovery_hours=executed.recovery_hours,

            previous_trainings=CoachContextBuilder._previous_trainings(
                history,
            ),

            # Progresso da semana = km REALMENTE acumulados na semana ISO
            # do treino executado, comparado à meta. Antes vinha a média de
            # 4 semanas (capacidade) contra 1.08× ela mesma -> dava ~92%
            # fixo e o coach dizia "próximo de concluir o volume" sempre,
            # mesmo em treino extra com a semana já fechada (bug do Renato).
            weekly_volume=CoachContextBuilder._current_week_volume(
                history,
                executed,
            ),

            # Meta = volume PRESCRITO da semana (plano). A recomendação da
            # avaliação vem da média histórica ×1.08; pra atleta NOVO (só a
            # semana atual no histórico) a média = o volume da semana, então
            # meta ≈ volume ×1.08 -> sempre ~92% ("próximo de concluir")
            # mesmo tendo feito 1 de 3 treinos. O volume do plano é fixo e
            # real. Fallback pra recomendação quando o plano não traz volume
            # (ex.: plano vazio de treinador externo ainda sem print).
            weekly_goal=(
                plan_weekly_volume
                if plan_weekly_volume and plan_weekly_volume > 0
                else assessment.recommended_weekly_volume
            ),

            consistency=assessment.consistency,

            history_weeks=ConsistencyCalculator.evaluated_weeks(
                history,
            ),

            injuries=runner.injuries,

        )

    @staticmethod
    def _current_week_volume(
        history: TrainingHistory,
        executed: EnrichedActivity,
    ) -> float:
        """Km somados na semana ISO (seg–dom) a que o treino executado
        pertence. É o volume REAL da semana, não a média histórica — é o
        que faz sentido pra dizer quanto falta pra fechar a semana."""

        week_key = activity_date(executed.activity).isocalendar()[:2]

        total_m = sum(
            activity.distance
            for activity in history.activities
            if activity_date(activity).isocalendar()[:2] == week_key
        )

        return round(total_m / 1000, 1)

    @staticmethod
    def _previous_trainings(
        history: TrainingHistory,
    ) -> list:

        if len(history.activities) <= 1:

            return []

        return history.activities[1:]
