from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.runner_metrics import RunnerMetricsBuilder
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.domain.entities.training_goal import TrainingGoal
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
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

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = RunnerMetricsBuilder.build(
            history,
        )

        goal = TrainingGoal(
            name=runner.goal,
            distance_km=10,
            target_time=runner.target_time,
            race_date=None,
        )

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
        )

        message = WeeklyPlanMessageFormatter.format(
            runner.name,
            plan,
        )

        await NotificationService.send_training_feedback(
            phone=runner.phone,
            message=message,
        )
