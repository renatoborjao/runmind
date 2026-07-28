"""Detecta treinos novos no Garmin e dispara a análise. O Garmin não-oficial
não tem webhook (como o Strava), então checamos por polling a cada ~10 min.

Proteção contra backfill: na PRIMEIRA passada de um atleta recém-conectado,
o histórico é marcado como 'já processado' sem analisar — senão a gente
mandaria feedback de treinos antigos de uma vez."""

from datetime import timedelta
from pathlib import Path

from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.core.clock import today_local
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)
from app.infrastructure.persistence.cross_training_repository import (
    CrossTrainingRepository,
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
    def seed_cross_training(profile: str, days_back: int = 35) -> int:
        """Backfill do contador de carga do corpo: varre as atividades do
        Garmin e guarda o CROSS-TRAINING (não-corrida) dos últimos `days_back`
        dias — pra o ACWR já nascer com o estresse real, sem esperar acumular.
        Não analisa nada (a corrida já tem seu arquivo). Retorna quantas
        guardou. Ver [[project_analise_corpo_garmin]]."""

        if not GarminClient.is_connected(profile):

            return 0

        garmin = GarminClient.connect(profile)

        cutoff = today_local() - timedelta(days=days_back)

        repo = CrossTrainingRepository()

        stored = 0

        start = 0

        page = 20

        while True:

            batch = garmin.get_activities(start, page) or []

            if not batch:

                break

            captured = []

            reached_cutoff = False

            for item in batch:

                activity = GarminActivitySource.summary_from_item(item)

                if activity.start_date.date() < cutoff:

                    reached_cutoff = True

                    break

                type_key = str(
                    (item.get("activityType") or {}).get("typeKey") or ""
                )

                # tipo ausente ou corrida/caminhada: fora do contador de corpo
                # (a corrida já vive no arquivo dela)
                if not type_key or is_foot_sport(
                    GarminActivitySource._sport(type_key)
                ):

                    continue

                if activity.moving_time > 0:

                    captured.append(activity)

            if captured:

                repo.upsert_many(profile, captured)

                stored += len(captured)

            if reached_cutoff or len(batch) < page:

                break

            start += page

        return stored

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

            # NÃO-corrida (musculação/natação/Hyrox...): entra SÓ no contador
            # de carga do corpo e para por aqui — nunca vira análise de
            # corrida. Corrida/caminhada segue pro fluxo normal.
            if GarminActivityPoller._capture_cross_training(profile, item):

                continue

            await GarminActivityPoller._analyze(profile, activity_id)

    @staticmethod
    def _capture_cross_training(profile: str, item: dict) -> bool:
        """Se o item da lista é NÃO-corrida, grava no contador de carga do
        corpo (só duração + FC) e devolve True (o chamador não segue pra
        análise). False = é corrida/caminhada (segue o fluxo normal) ou falhou.
        Best-effort: falhar aqui nunca derruba o poll de corrida. Ver
        [[project_analise_corpo_garmin]]."""

        try:

            type_dto = item.get("activityType") or {}

            type_key = str(type_dto.get("typeKey") or "")

            # tipo ausente/ilegível no item: NÃO arrisca desviar uma corrida —
            # deixa o _analyze (deep-fetch, fonte autoritativa do sport) decidir
            if not type_key:

                return False

            if is_foot_sport(GarminActivitySource._sport(type_key)):

                return False

            activity = GarminActivitySource.summary_from_item(item)

            if activity.moving_time > 0:

                CrossTrainingRepository().upsert_many(profile, [activity])

            # capturado (mesmo sem duração): não é corrida, não analisa
            return True

        except Exception as e:

            print(f"Garmin: falha ao capturar cross-training de '{profile}': {e}")

            return False

    @staticmethod
    async def _analyze(profile: str, activity_id: int) -> None:

        try:

            # treinador externo: as voltas do Garmin não vêm do nosso push,
            # então o _exact_interval aplica o filtro de tiros-caminhada
            runner = RunnerProfileRepository().load(profile)

            activity = GarminActivitySource.fetch(
                profile,
                activity_id,
                external_coach=bool(getattr(runner, "external_coach", False)),
            )

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
