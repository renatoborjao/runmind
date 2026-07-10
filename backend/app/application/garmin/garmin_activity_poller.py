"""Detecta treinos novos no Garmin e dispara a análise. O Garmin não-oficial
não tem webhook (como o Strava), então checamos por polling a cada ~10 min.

Proteção contra backfill: na PRIMEIRA passada de um atleta recém-conectado,
o histórico é marcado como 'já processado' sem analisar — senão a gente
mandaria feedback de treinos antigos de uma vez."""

from pathlib import Path

from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)
from app.infrastructure.persistence.processed_activity_guard import (
    ProcessedActivityGuard,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# quantas atividades recentes olhar por passada
_RECENT_LIMIT = 8


def _seeded_marker(profile: str) -> Path:

    return GarminClient.token_dir(profile) / "seeded"


class GarminActivityPoller:

    @staticmethod
    async def poll_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            if not GarminClient.is_connected(profile):

                continue

            try:

                await GarminActivityPoller._poll_one(profile)

            except Exception as e:

                print(f"Garmin poll falhou para '{profile}': {e}")

    @staticmethod
    async def _poll_one(profile: str) -> None:

        garmin = GarminClient.connect(profile)

        activities = garmin.get_activities(0, _RECENT_LIMIT) or []

        guard = ProcessedActivityGuard()

        marker = _seeded_marker(profile)

        seeded = marker.exists()

        for item in activities:

            activity_id = item.get("activityId")

            if activity_id is None:

                continue

            # primeira passada: só marca (não analisa histórico antigo)
            if not seeded:

                guard.check_and_mark(activity_id)

                continue

            # já processado: pula (dedup)
            if not guard.check_and_mark(activity_id):

                continue

            await GarminActivityPoller._analyze(profile, activity_id)

        if not seeded:

            marker.write_text("1", encoding="utf-8")

    @staticmethod
    async def _analyze(profile: str, activity_id: int) -> None:

        try:

            activity = GarminActivitySource.fetch(profile, activity_id)

            if not is_foot_sport(activity.sport):

                print(f"Garmin {activity_id}: sport ignorado ({activity.sport})")

                return

            await TrainingCompletedEvent.execute(
                profile=profile,
                activity=activity,
            )

        except Exception as e:

            # solta a marca pra tentar de novo na próxima passada
            ProcessedActivityGuard().unmark(activity_id)

            print(f"Garmin: falha ao analisar {activity_id}: {e}")
