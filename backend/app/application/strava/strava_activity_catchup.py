"""Rede de segurança pra atleta SÓ-STRAVA: quando o servidor cai, o webhook do
Strava se perde (o Strava reentrega poucas vezes e desiste). Este catch-up
varre as atividades recentes do atleta e analisa as que ainda NÃO passaram
(dedup pelo MESMO ProcessedActivityGuard do webhook) — recuperando o feedback
perdido no downtime. Roda no startup (fecha o buraco da queda) e periodicamente.

Atleta analisado via Garmin NÃO entra aqui: pra ele o webhook Strava já vira
gatilho do poller Garmin (outra fonte, outro id) — analisaria 2x."""

from pathlib import Path

from app.application.events.training_completed import TrainingCompletedEvent
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.processed_activity_guard import (
    ProcessedActivityGuard,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.storage.token_store import TokenStore

_RECENT_LIMIT = 10

_SEED_DIR = Path(__file__).resolve().parents[3] / "storage" / "strava_catchup"


def _seeded_marker(profile: str) -> Path:

    return _SEED_DIR / f"{profile}.seeded"


class StravaActivityCatchup:

    @staticmethod
    async def run_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await StravaActivityCatchup.run_one(profile)

            except Exception as e:

                print(f"Strava catch-up falhou para '{profile}': {e}")

    @staticmethod
    async def run_one(profile: str) -> None:

        # precisa do Strava conectado
        if TokenStore(profile).load() is None:

            return

        # analisado via Garmin: coberto pelo poller + gatilho do webhook —
        # este catch-up analisaria a mesma corrida uma 2ª vez (id do Strava)
        if (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            return

        client = StravaClient(profile)

        activities = await client.get_last_activities(limit=_RECENT_LIMIT)

        guard = ProcessedActivityGuard()

        # primeira passada (recurso recém-ligado / atleta recém-conectado):
        # SÓ MARCA as recentes, sem analisar — não despeja o histórico antigo
        marker = _seeded_marker(profile)

        if not marker.exists():

            for activity in activities:

                guard.check_and_mark(activity.id)

            _SEED_DIR.mkdir(parents=True, exist_ok=True)

            marker.write_text("1", encoding="utf-8")

            return

        # do mais antigo pro mais novo, pra o feedback sair em ordem
        for activity in reversed(activities):

            # já processado (webhook ou passada anterior): pula
            if not guard.check_and_mark(activity.id):

                continue

            await StravaActivityCatchup._analyze(profile, activity.id)

    @staticmethod
    async def _analyze(profile: str, activity_id: int) -> None:

        try:

            client = StravaClient(profile)

            activity = await client.get_activity(activity_id)

            # stream segundo-a-segundo (revela tiros curtos); indisponível
            # nunca derruba o fluxo
            try:

                activity.raw["_streams"] = await client.get_activity_streams(
                    activity_id,
                )

            except Exception as stream_error:

                print(f"Streams indisponíveis p/ {activity_id}: {stream_error}")

            if not is_foot_sport(activity.sport):

                print(
                    f"Strava catch-up {activity_id}: sport ignorado "
                    f"({activity.sport})"
                )

                return

            # corrida sem distância (esteira/HIIT sem sensor): não dá pra
            # analisar pace — pula (igual ao webhook)
            if not activity.distance:

                print(f"Strava catch-up {activity_id}: sem distância, pulado")

                return

            await TrainingCompletedEvent.execute(
                profile=profile,
                activity=activity,
            )

        except Exception as e:

            # solta a marca pra tentar de novo na próxima passada
            ProcessedActivityGuard().unmark(activity_id)

            print(f"Strava catch-up: falha ao analisar {activity_id}: {e}")
