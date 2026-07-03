from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.context.coach_context_builder import (
    CoachContextBuilder,
)
from app.application.coach.pipeline.coach_pipeline import (
    CoachPipeline,
)
from app.application.history.activity_enricher import (
    ActivityEnricher,
)
from app.application.history.runner_metrics import (
    RunnerMetricsBuilder,
)
from app.application.planner.weekly_plan_service import (
    WeeklyPlanService,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.weekdays import (
    weekday_name,
)
from app.domain.entities.activity import (
    Activity,
)
from app.domain.entities.training_goal import (
    TrainingGoal,
)


class CoachAnalysisBuilder:
    """Parte read-only da análise do coach: carrega os dados, monta o
    contexto e executa o CoachPipeline. Não persiste nada além do plano
    semanal (get_or_generate) — pode ser chamado repetidamente."""

    @staticmethod
    async def build(
        profile: str = "renato",
        activity: Activity | None = None,
    ) -> dict:

        # --------------------------------------------------
        # Histórico
        # --------------------------------------------------

        history = await LoadTrainingHistory.execute(
            profile=profile,
            activity=activity,
        )

        # --------------------------------------------------
        # Perfil
        # --------------------------------------------------

        runner = LoadRunnerProfile.execute(
            profile,
        )

        # --------------------------------------------------
        # Assessment
        # --------------------------------------------------

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        # --------------------------------------------------
        # Objetivo
        # --------------------------------------------------

        goal = TrainingGoal(
            name=runner.goal,
            distance_km=10,
            target_time=runner.target_time,
            race_date=None,
        )

        # --------------------------------------------------
        # Métricas
        # --------------------------------------------------

        metrics = RunnerMetricsBuilder.build(
            history,
        )

        # --------------------------------------------------
        # Plano (persistido, uma vez por semana)
        # --------------------------------------------------

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
        )

        # --------------------------------------------------
        # Atividade enriquecida
        # --------------------------------------------------

        enriched = ActivityEnricher.enrich(
            history.latest,
            metrics,
        )

        # --------------------------------------------------
        # Procura treino pelo dia
        # --------------------------------------------------

        activity_day = weekday_name(
            enriched.activity.start_date,
        )

        planned_session = plan.find_session_by_day(
            activity_day,
        )

        # --------------------------------------------------
        # Fallback pela distância
        # --------------------------------------------------

        if planned_session is None:

            executed_distance = (
                enriched.activity.distance / 1000
            )

            planned_session = plan.find_best_session(
                executed_distance,
            )

        if planned_session is None:

            raise Exception(
                "Nenhum treino planejado encontrado."
            )

        # --------------------------------------------------
        # Coach
        # --------------------------------------------------

        coach_context = CoachContextBuilder.build(
            runner=runner,
            planned=planned_session,
            executed=enriched,
            history=history,
            assessment=assessment,
        )

        coach_analysis = CoachPipeline.execute(
            coach_context,
        )

        return {

            "runner": runner,

            "history": history,

            "assessment": assessment,

            "plan": plan,

            "planned_session": planned_session,

            "enriched": enriched,

            "context": coach_context,

            "analysis": coach_analysis,

        }
