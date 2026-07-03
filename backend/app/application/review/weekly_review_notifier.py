from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.review.weekly_review_builder import (
    WeeklyReviewBuilder,
)
from app.application.review.weekly_review_message_formatter import (
    WeeklyReviewMessageFormatter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# cobre as 8 semanas da tendência com folga
HISTORY_LIMIT = 60


class WeeklyReviewNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await WeeklyReviewNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha ao enviar resumo semanal para "
                    f"'{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
            limit=HISTORY_LIMIT,
        )

        review = WeeklyReviewBuilder.build(
            runner,
            history,
        )

        message = WeeklyReviewMessageFormatter.format(
            runner.name,
            review,
        )

        if message is None:

            return

        await NotificationService.send_training_feedback(
            phone=runner.phone,
            message=message,
        )
