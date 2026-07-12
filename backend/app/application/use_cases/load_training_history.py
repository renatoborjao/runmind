from app.domain.entities.activity import Activity
from app.domain.entities.training_history import (
    TrainingHistory,
)
from app.domain.value_objects.sports import is_foot_sport
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
        profile: str = "renato",
        limit: int = 30,
        activity: Activity | None = None,
    ) -> TrainingHistory:

        if activity is not None:

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

        LoadTrainingHistory._archive(
            profile,
            activities,
        )

        return TrainingHistory(

            activities=activities

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