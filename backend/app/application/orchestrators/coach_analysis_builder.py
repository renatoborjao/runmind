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
from app.application.history.metrics_resolver import (
    MetricsResolver,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
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
from app.domain.entities.activity import (
    Activity,
)
from app.application.use_cases.build_training_goal import (
    BuildTrainingGoal,
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

        goal = BuildTrainingGoal.execute(runner)

        # --------------------------------------------------
        # Métricas
        # --------------------------------------------------

        metrics = MetricsResolver.resolve(
            runner,
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
        # Casa o treino com a sessão que ele cumpriu — por
        # DISTÂNCIA, não por dia (plano é guia, não obrigação
        # de dia). Sobra além das sessões da semana = extra.
        # --------------------------------------------------

        planned_session = WeeklyPlanMatcher.match(
            plan,
            history.activities,
            enriched.activity,
        )

        # --------------------------------------------------
        # Próxima sessão futura (para o "próximo treino")
        # --------------------------------------------------

        next_planned = plan.next_session_after(
            enriched.activity.start_date.date(),
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
            next_planned=next_planned,
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
