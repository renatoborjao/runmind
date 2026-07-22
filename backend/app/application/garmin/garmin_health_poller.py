"""Ingere o retrato diário de saúde do Garmin (sono/HRV/stress/prontidão...)
1x por dia por atleta. Camada 1: só junta o dado no disco, SEM IA e SEM
custo — a análise vem depois.

Gentileza com a API não-oficial (risco de rate-limit): puxa só o dia ANTERIOR
(já fechado) e, se já tiver esse dia guardado, nem conecta no Garmin. Roda de
hora em hora, mas o dedup por data faz virar UM pull/atleta/dia de verdade —
e resiliente a máquina que dorme (pega assim que ela estiver ligada)."""

import time
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


# backfill: teto de segurança de dias pra trás, e quantos dias VAZIOS
# seguidos (antes de o atleta ter o relógio) fazem parar. Pausa entre pulls
# pra ser gentil com a API não-oficial (evita rate-limit/flag no lote inicial).
_SEED_MAX_DAYS = 60
_SEED_STOP_AFTER_EMPTY = 3
_SEED_PACE_SECONDS = 1.2


class GarminHealthPoller:

    @staticmethod
    def seed_history(
        profile: str,
        repo: GarminHealthRepository | None = None,
    ) -> int:
        """Backfill único: puxa os retratos diários pra trás até bater no
        começo do histórico do relógio (para depois de alguns dias vazios
        seguidos — não adianta puxar de antes de o atleta ter o Garmin).
        Pula dias já guardados. Devolve quantos dias novos gravou.

        Roda como AÇÃO ÚNICA (script), não no tick recorrente: o pacing usa
        sleep bloqueante de propósito, pra não martelar a API."""

        repo = repo or GarminHealthRepository()

        runner = RunnerProfileRepository().load(profile)

        today = now_in(getattr(runner, "timezone", None)).date()

        pulled = 0

        empty_streak = 0

        for n in range(1, _SEED_MAX_DAYS + 1):

            day = (today - timedelta(days=n)).isoformat()

            if repo.has_date(profile, day):

                empty_streak = 0

                continue

            health = GarminHealthSource.fetch(profile, day)

            if not health.has_data:

                empty_streak += 1

                if empty_streak >= _SEED_STOP_AFTER_EMPTY:

                    break

                time.sleep(_SEED_PACE_SECONDS)

                continue

            repo.upsert(profile, health)

            pulled += 1

            empty_streak = 0

            time.sleep(_SEED_PACE_SECONDS)

        return pulled

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
