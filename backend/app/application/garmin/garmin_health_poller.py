"""Ingere o retrato diário de saúde do Garmin (sono/HRV/stress/prontidão...)
1x por dia por atleta. Camada 1: só junta o dado no disco, SEM IA e SEM
custo — a análise vem depois.

Gentileza com a API não-oficial (risco de rate-limit): puxa só o dia ANTERIOR
(já fechado) e, se já tiver esse dia guardado, nem conecta no Garmin. Roda de
hora em hora, mas o dedup por data faz virar UM pull/atleta/dia de verdade —
e resiliente a máquina que dorme (pega assim que ela estiver ligada)."""

from datetime import timedelta

from app.core.clock import now_in
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class GarminHealthPoller:

    @staticmethod
    async def poll_all() -> None:

        repo = GarminHealthRepository()

        for profile in RunnerProfileRepository().list_all():

            # mesmo gate da análise de treino: conectado E válvula ligada
            if not (
                GarminClient.is_connected(profile)
                and GarminClient.analysis_enabled(profile)
            ):

                continue

            try:

                GarminHealthPoller.poll_one(profile, repo)

            except Exception as e:

                print(f"Garmin health poll falhou para '{profile}': {e}")

    @staticmethod
    def poll_one(
        profile: str,
        repo: GarminHealthRepository | None = None,
    ) -> None:

        repo = repo or GarminHealthRepository()

        runner = RunnerProfileRepository().load(profile)

        # ontem no fuso do atleta: o dia de ontem já está fechado (sono da
        # noite, stress do dia inteiro), ao contrário de "hoje" que ainda enche
        yesterday = (
            now_in(getattr(runner, "timezone", None)).date() - timedelta(days=1)
        ).isoformat()

        # já temos esse dia: nem bate no Garmin (dedup + gentileza)
        if repo.has_date(profile, yesterday):

            return

        health = GarminHealthSource.fetch(profile, yesterday)

        repo.upsert(profile, health)
