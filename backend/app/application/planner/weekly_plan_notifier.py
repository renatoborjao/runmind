from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.coach.planning.plan_realism_reviewer import (
    PlanRealismReviewer,
)
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WeeklyPlanNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await WeeklyPlanNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha ao enviar plano semanal para "
                    f"'{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner = LoadRunnerProfile.execute(profile)

        # atleta com treinador humano: pede o treino da semana em vez
        # de gerar plano
        if runner.external_coach:

            await WeeklyPlanNotifier._notify_external(
                profile,
                runner,
            )

            return

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
        )

        # IA revisora: marca sessões irreais pra este atleta (uma vez por
        # semana); se a IA falhar, o plano segue intacto.
        plan = await PlanRealismReviewer.ensure_reviewed(
            profile,
            runner,
            plan,
        )

        message = WeeklyPlanMessageFormatter.format(
            runner.name,
            plan,
        )

        await NotificationService.send(
            runner,
            message,
        )

    @staticmethod
    async def _notify_external(
        profile: str,
        runner,
    ) -> None:

        plan = WeeklyPlanRepository().load(profile)

        current_week = WeeklyPlanService._week_start(today_local())

        if plan is not None and plan.week_start == current_week:

            # plano da semana já enviado: só reapresenta
            message = WeeklyPlanMessageFormatter.format(
                runner.name,
                plan,
            )

        else:

            message = (
                f"Bom domingo, {runner.name}! 🏃\n\n"
                "Me manda um print, foto ou PDF do treino desta "
                "semana do seu treinador pra eu acompanhar seus "
                "treinos e te dar feedback. 📸"
            )

        await NotificationService.send(
            runner,
            message,
        )
