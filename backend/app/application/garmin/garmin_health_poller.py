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
from app.domain.entities.daily_health import DailyHealth
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.race_prediction_repository import (
    RacePredictionRepository,
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

    # varredura do VO₂máx: quantos dias pra trás revisitar e o passo gentil.
    # O Garmin recalcula o VO₂máx esporádico e às vezes com ATRASO — o poll de
    # "ontem, 1x" perde esses valores pra sempre (o dado existe na API mas nunca
    # entra na série). A varredura revisita os dias recentes e preenche a lacuna.
    _VO2_SCAN_DAYS = 30
    _VO2_SCAN_PACE_SECONDS = 1.0

    @staticmethod
    def sync_vo2max(
        profile: str,
        days: int = _VO2_SCAN_DAYS,
        repo: GarminHealthRepository | None = None,
    ) -> int:
        """Preenche o VO₂máx faltante nos últimos `days`: varre get_max_metrics
        dia a dia e, onde há medição, MESCLA o valor no snapshot do dia (sem
        tocar em sono/HRV/stress já gravados). Conserta o buraco que fazia o
        coach ficar cego pro VO₂máx real do atleta. Devolve quantos preencheu.

        Ação idempotente: dia que já tem VO₂máx é pulado (nem bate na API)."""

        repo = repo or GarminHealthRepository()

        # VO₂máx é dado do GARMIN: só faz sentido pra quem tem o relógio
        # conectado E a análise ligada (mesmo gate do poll_all) — nunca bater
        # na API nem inserir dado pra quem não tem Garmin.
        if not (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            return 0

        garmin = GarminClient.connect(profile)

        if garmin is None:

            return 0

        runner = RunnerProfileRepository().load(profile)

        today = now_in(getattr(runner, "timezone", None)).date()

        by_date = {h.date: h for h in repo.load(profile)}

        filled = 0

        for n in range(1, days + 1):

            day = (today - timedelta(days=n)).isoformat()

            existing = by_date.get(day)

            # já temos o VO₂máx desse dia: nada a fazer, poupa a API
            if existing is not None and existing.vo2max is not None:

                continue

            value = GarminHealthSource.vo2max_for(garmin, day)

            time.sleep(GarminHealthPoller._VO2_SCAN_PACE_SECONDS)

            if value is None:

                continue

            # mescla no snapshot do dia (ou cria um só com o VO₂máx, se o dia
            # ainda não existir — has_data conta o VO₂máx, então vale guardar)
            health = existing or DailyHealth(date=day)

            health.vo2max = value

            repo.upsert(profile, health)

            by_date[day] = health

            filled += 1

        return filled

    # varredura da carga-de-vida/body battery: dado DIÁRIO, então o fetch de
    # ontem já o captura pra frente. Esta varredura só ENRIQUECE os dias
    # recentes que já existiam ANTES de o campo existir (senão a leitura de
    # recuperação ficaria semanas sem histórico). 1 chamada/dia (só o
    # get_user_summary), idempotente, mesmo gate do VO₂máx.
    _BODY_CTX_SCAN_DAYS = 7
    _BODY_CTX_PACE_SECONDS = 1.0

    @staticmethod
    def sync_body_context(
        profile: str,
        days: int = _BODY_CTX_SCAN_DAYS,
        repo: GarminHealthRepository | None = None,
    ) -> int:
        """Mescla carga de vida + body battery nos snapshots recentes que ainda
        não têm (get_user_summary). Só ENRIQUECE dias já rastreados — contexto
        não vale um dia novo. Idempotente: pula dia que já tem
        body_battery_most_recent. Devolve quantos enriqueceu."""

        repo = repo or GarminHealthRepository()

        # dado do GARMIN: só quem tem o relógio conectado + análise ligada
        if not (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            return 0

        garmin = GarminClient.connect(profile)

        if garmin is None:

            return 0

        runner = RunnerProfileRepository().load(profile)

        today = now_in(getattr(runner, "timezone", None)).date()

        by_date = {h.date: h for h in repo.load(profile)}

        filled = 0

        for n in range(1, days + 1):

            day = (today - timedelta(days=n)).isoformat()

            existing = by_date.get(day)

            # contexto NÃO cria dia novo — só enriquece o que já é snapshot real
            if existing is None:

                continue

            # já enriquecido: nada a fazer, poupa a API
            if existing.body_battery_most_recent is not None:

                continue

            ctx = GarminHealthSource.body_context_for(garmin, day)

            time.sleep(GarminHealthPoller._BODY_CTX_PACE_SECONDS)

            if not ctx:

                continue

            for attr, value in ctx.items():

                setattr(existing, attr, value)

            repo.upsert(profile, existing)

            filled += 1

        return filled

    @staticmethod
    def sync_race_predictions(
        profile: str,
        repo: RacePredictionRepository | None = None,
    ) -> bool:
        """Atualiza a previsão de prova (5K/10K/meia/maratona) do Garmin — o
        ESTADO atual, não série. Mesmo gate do VO₂máx (dado do relógio, só pra
        quem tem). Devolve se gravou uma projeção com dado."""

        # dado do GARMIN: só quem tem o relógio conectado + análise ligada
        if not (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            return False

        garmin = GarminClient.connect(profile)

        if garmin is None:

            return False

        prediction = GarminHealthSource.race_predictions_for(garmin)

        if not prediction.has_data:

            return False

        (repo or RacePredictionRepository()).save(profile, prediction)

        return True

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

        # série diária (sono/HRV/stress/RHR): só puxa se ainda não tiver ontem
        if not repo.has_date(profile, yesterday):

            health = GarminHealthSource.fetch(profile, yesterday)

            repo.upsert(profile, health)

        # ESTADO: o VO₂máx chega esporádico/atrasado — varre os dias recentes e
        # preenche as lacunas (barato: pula dias que já têm o valor). Sem isto o
        # coach fica cego pro VO₂máx real, que existe na API mas nunca entrava.
        GarminHealthPoller.sync_vo2max(profile, days=10, repo=repo)

        # CONTEXTO: carga de vida + body battery. O fetch de ontem já traz pra
        # frente; a varredura enriquece os dias recentes que existiam antes do
        # campo (idempotente, pula os já preenchidos).
        GarminHealthPoller.sync_body_context(profile, repo=repo)

        # ESTADO: previsão de prova (5K/10K/meia/maratona) do Garmin — atualiza
        # o snapshot atual (calibra meta/realismo do plano). Best-effort.
        GarminHealthPoller.sync_race_predictions(profile)
