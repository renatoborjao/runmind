from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.orchestrators.training_pipeline import (
    TrainingPipeline,
)
from app.domain.entities.activity import (
    Activity,
)


class TrainingCompletedEvent:

    @staticmethod
    async def execute(
        profile: str = "renato",
        activity: Activity | None = None,
    ):

        result = await TrainingPipeline.execute(
            profile=profile,
            activity=activity,
        )

        runner = result["runner"]

        await NotificationService.send(
            runner,
            result["message"],
        )

        return result