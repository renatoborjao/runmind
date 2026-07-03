from app.domain.entities.activity import Activity
from app.domain.entities.training_history import (
    TrainingHistory,
)
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)


class LoadTrainingHistory:

    @staticmethod
    async def execute(
        profile: str = "renato",
        limit: int = 30,
        activity: Activity | None = None,
    ) -> TrainingHistory:

        if activity is not None:

            return TrainingHistory(

                activities=[activity]

            )

        client = StravaClient(
            profile
        )

        activities = await client.get_last_activities(
            limit
        )

        return TrainingHistory(

            activities=activities

        )