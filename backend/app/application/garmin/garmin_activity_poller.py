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
    def seed_history(profile: str) -> None:
        """Marca as atividades recentes como 'já vistas' SEM analisar, e
        grava o marcador. Chamado no LOGIN — assim o histórico antigo não
        vira feedback retroativo, e qualquer treino DEPOIS do login é
        analisado normalmente (pelo gatilho do Strava ou pelo poller)."""

        if not GarminClient.is_connected(profile):

            return

        try:

            garmin = GarminClient.connect(profile)

            guard = ProcessedActivityGuard()

            for item in garmin.get_activities(0, _RECENT_LIMIT) or []:

                activity_id = item.get("activityId")

                if activity_id is not None:

                    guard.check_and_mark(activity_id)

            _seeded_marker(profile).write_text("1", encoding="utf-8")

        except Exception as e:

            print(f"Garmin: falha ao semear histórico de '{profile}': {e}")

    @staticmethod
    async def poll_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            # análise via Garmin exige conexão E a válvula ligada
            if not (
                GarminClient.is_connected(profile)
                and GarminClient.analysis_enabled(profile)
            ):

                continue

            try:

                await GarminActivityPoller.poll_one(profile)

            except Exception as e:

                print(f"Garmin poll falhou para '{profile}': {e}")

    @staticmethod
    async def poll_one(profile: str) -> None:
        """Analisa treinos NOVOS do atleta (deduplicados). Serve tanto pro
        poller de 10 min quanto pro gatilho instantâneo do webhook Strava."""

        # atleta sem seed (logou antes deste fluxo): seed agora, sem
        # analisar — evita despejar o histórico antigo de uma vez
        if not _seeded_marker(profile).exists():

            GarminActivityPoller.seed_history(profile)

            return

        garmin = GarminClient.connect(profile)

        activities = garmin.get_activities(0, _RECENT_LIMIT) or []

        guard = ProcessedActivityGuard()

        for item in activities:

            activity_id = item.get("activityId")

            if activity_id is None:

                continue

            # já processado: pula (dedup — cobre poller + gatilho)
            if not guard.check_and_mark(activity_id):

                continue

            await GarminActivityPoller._analyze(profile, activity_id)

    @staticmethod
    async def _analyze(profile: str, activity_id: int) -> None:

        try:

            activity = GarminActivitySource.fetch(profile, activity_id)

            if not is_foot_sport(activity.sport):

                print(f"Garmin {activity_id}: sport ignorado ({activity.sport})")

                return

            # corrida sem distância (esteira/HIIT sem sensor): não dá pra
            # analisar pace — pula sem crashar (o enricher dividiria por zero)
            if not activity.distance:

                print(f"Garmin {activity_id}: sem distância, pulado")

                return

            await TrainingCompletedEvent.execute(
                profile=profile,
                activity=activity,
            )

        except Exception as e:

            # solta a marca pra tentar de novo na próxima passada
            ProcessedActivityGuard().unmark(activity_id)

            print(f"Garmin: falha ao analisar {activity_id}: {e}")
