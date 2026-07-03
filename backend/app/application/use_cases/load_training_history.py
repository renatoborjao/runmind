from app.domain.entities.activity import Activity
from app.domain.entities.training_history import (
    TrainingHistory,
)
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.storage.token_store import TokenStore


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

        # atleta sem Strava conectado: histórico vazio, sem erro —
        # o MetricsResolver/assessment cuidam do plano inicial
        if TokenStore(profile).load() is None:

            return TrainingHistory(activities=[])

        client = StravaClient(
            profile
        )

        activities = await client.get_last_activities(
            limit
        )

        # só treinos a pé entram no histórico — bike/natação/musculação
        # poluiriam volume, consistência e comparações
        activities = [
            activity
            for activity in activities
            if is_foot_sport(activity.sport)
        ]

        return TrainingHistory(

            activities=activities

        )