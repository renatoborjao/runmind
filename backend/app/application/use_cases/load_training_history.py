from app.domain.entities.activity import Activity
from app.domain.entities.training_history import (
    TrainingHistory,
)
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.storage.token_store import TokenStore


class LoadTrainingHistory:

    @staticmethod
    async def execute(
        profile: str,
        limit: int = 30,
        activity: Activity | None = None,
    ) -> TrainingHistory:

        if activity is not None:

            LoadTrainingHistory._fill_hr_zones(profile, activity)

            LoadTrainingHistory._archive(
                profile,
                [activity],
            )

            # Histórico = arquivo permanente (tudo que já passou) + a
            # atividade recém-concluída à frente (newest-first). Antes
            # retornava só [activity], então TODA análise pós-treino (Strava
            # E Garmin passam a atividade) enxergava 1 corrida só — volume,
            # consistência e comparações degeneravam ("poucas semanas pra
            # avaliar" mesmo com meses de histórico arquivado).
            archived = ActivityArchiveRepository().load_activities(profile)

            past = sorted(
                (
                    past_activity
                    for past_activity in archived
                    if past_activity.id != activity.id
                ),
                key=lambda past_activity: past_activity.start_date,
                reverse=True,
            )

            return TrainingHistory(
                activities=LoadTrainingHistory._dedup(
                    [activity] + past,
                ),
            )

        # ---- CARGA BASE: histórico AGNÓSTICO DE FONTE ----
        # base permanente (arquivo unificado Strava+Garmin, acumulado a cada
        # passada) + o recém-buscado da fonte conectada. Assim o coach enxerga
        # o atleta mesmo SEM Strava (independência do Strava). Ver
        # [[project_independencia_strava]] e [[project_garmin_strava_dedup]].
        archived = ActivityArchiveRepository().load_activities(profile)

        live: list[Activity] = []

        # Strava conectado: ele já recebe o Garmin sincronizado, então uma
        # fonte ao vivo basta (mantém o comportamento anterior, sem custo novo).
        if TokenStore(profile).load() is not None:

            try:

                live = await StravaClient(profile).get_last_activities(limit)

            except Exception as e:

                print(f"Strava: falha ao carregar histórico de '{profile}': {e}")

        # Garmin-only: sem Strava, puxa o histórico DIRETO do relógio — antes
        # isto voltava VAZIO e o coach ficava cego pra quem não tinha Strava.
        elif GarminClient.is_connected(profile):

            try:

                live = GarminActivitySource.recent(profile, limit)

            except Exception as e:

                print(f"Garmin: falha ao carregar histórico de '{profile}': {e}")

        # só treinos a pé entram no histórico — bike/natação/musculação
        # poluiriam volume, consistência e comparações
        live = [
            activity
            for activity in live
            if is_foot_sport(activity.sport)
        ]

        LoadTrainingHistory._archive(
            profile,
            live,
        )

        # une o recém-buscado com o arquivo permanente, colapsa a MESMA corrida
        # vinda de fontes diferentes (dedup), newest-first, corta no limite
        merged = LoadTrainingHistory._dedup(
            sorted(
                (a for a in live + archived if is_foot_sport(a.sport)),
                key=lambda a: a.start_date,
                reverse=True,
            )
        )

        return TrainingHistory(

            activities=merged[:limit]

        )

    @staticmethod
    def _dedup(
        activities: list[Activity],
    ) -> list[Activity]:
        """Colapsa o MESMO treino vindo de fontes diferentes. Como todo
        treino do Garmin sincroniza pro Strava, a mesma corrida pode existir
        nas duas fontes (ids diferentes, ~3h de offset de fuso) numa
        transição de fonte. Mantém a 1ª ocorrência — a lista vem newest-first,
        então o treino recém-concluído (dados completos) ganha.

        Tolerância APERTADA de propósito pra não fundir dois treinos reais do
        mesmo dia: exige mesma DATA local + distância ~igual (0,5%) + tempo em
        movimento ~igual (2%). Corridas distintas raramente batem os três."""

        kept: list[Activity] = []

        for activity in activities:

            if any(
                LoadTrainingHistory._same_run(activity, other)
                for other in kept
            ):

                continue

            kept.append(activity)

        return kept

    @staticmethod
    def _same_run(
        a: Activity,
        b: Activity,
    ) -> bool:

        if a.id == b.id:

            return True

        if a.start_date.date() != b.start_date.date():

            return False

        biggest_dist = max(a.distance, b.distance, 1.0)

        if abs(a.distance - b.distance) > 0.005 * biggest_dist:

            return False

        biggest_time = max(a.moving_time, b.moving_time, 1)

        if abs(a.moving_time - b.moving_time) > 0.02 * biggest_time:

            return False

        return True

    @staticmethod
    def _fill_hr_zones(profile: str, activity: Activity) -> None:
        """Treino que chega SEM distribuição de zonas (Strava — o Garmin já
        traz a do relógio) ganha a sua pelo stream de FC, na régua única do
        atleta ([[HrZoneResolver]]). Alimenta gráfico, mensagem e carga.
        Best-effort: nunca derruba a análise."""

        if activity.hr_zone_minutes is not None:

            return

        heartrate = ((activity.raw or {}).get("_streams") or {}).get("heartrate")

        if not heartrate:

            return

        try:

            from app.application.history.hr_zone_resolver import (
                HrZoneResolver,
            )
            from app.infrastructure.persistence.runner_profile_repository import (
                RunnerProfileRepository,
            )

            zones = HrZoneResolver.for_profile(
                profile,
                RunnerProfileRepository().load(profile),
                ActivityArchiveRepository().load_activities(profile) + [activity],
            )

            if zones is not None:

                activity.hr_zone_minutes = zones.minutes(
                    heartrate, activity.moving_time
                )

        except Exception as e:

            print(f"Zonas de FC indisponíveis p/ {activity.id}: {e}")

    @staticmethod
    def _archive(
        profile: str,
        activities: list[Activity],
    ) -> None:

        # falha no arquivamento nunca derruba o fluxo principal
        try:

            ActivityArchiveRepository().upsert_many(
                profile,
                activities,
            )

        except Exception as e:

            print(
                f"Falha ao arquivar atividades de '{profile}': {e}"
            )