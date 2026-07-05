from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan


class CurrentPlanProvider:
    """Monta (perfil, plano da semana) de um atleta — o mesmo caminho
    determinístico usado pelo plano de domingo e pela conversa, num único
    lugar reutilizável (lembrete matinal, 'próximo treino' etc.)."""

    @staticmethod
    async def for_profile(
        profile: str,
        force: bool = False,
    ) -> tuple[RunnerProfile, TrainingPlan]:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            force=force,
            history=history,
        )

        return runner, plan
