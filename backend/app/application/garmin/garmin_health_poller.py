"""Ingere o retrato diário de saúde do Garmin (sono/HRV/stress/prontidão...)
1x por dia por atleta. Camada 1: só junta o dado no disco, SEM IA e SEM
custo — a análise vem depois.

Gentileza com a API não-oficial (risco de rate-limit): finaliza o dia FECHADO
(ontem) UMA vez e insiste no de HOJE só enquanto a leitura da manhã (SONO) não
caiu — o dedup por data/sono faz virar poucos pulls/atleta/dia de verdade. A
leitura da manhã roda num tick FREQUENTE (a cada 15 min) pra o sono da noite
aparecer logo que o relógio sincroniza; os scans caros (VO₂/body-context/prova)
ficam no tick horário. Ver GarminHealthPoller.poll_one e weekly_plan_scheduler."""

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

# leitura da manhã (hoje): até que HORA local ainda vale insistir no pull de
# hoje esperando o SONO da noite cair. O Garmin costuma processar o sono 1-2h
# depois de o atleta acordar; depois deste corte, quem ainda não registrou sono
# provavelmente dormiu sem o relógio — para de bater na API (o dia é finalizado
# amanhã, no passo (1)). Cobre quem acorda até ~meio-dia sem martelar a API.
_MORNING_SLEEP_CUTOFF_HOUR = 14


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
    async def poll_all(recovery_only: bool = False) -> None:

        repo = GarminHealthRepository()

        for profile in RunnerProfileRepository().list_all():

            # mesmo gate da análise de treino: conectado E válvula ligada
            if not (
                GarminClient.is_connected(profile)
                and GarminClient.analysis_enabled(profile)
            ):

                continue

            try:

                GarminHealthPoller.poll_one(
                    profile, repo, recovery_only=recovery_only
                )

            except Exception as e:

                print(f"Garmin health poll falhou para '{profile}': {e}")

    @staticmethod
    def _merge(existing: DailyHealth | None, fresh: DailyHealth) -> DailyHealth:
        """Mescla o snapshot novo sobre o que já havia: só sobrescreve campo COM
        valor (não-None), pra um endpoint que não mediu (None) nunca apagar o que
        outra passada já trouxe. Sem base anterior, é o próprio snapshot novo.
        `date`/`is_final` são controlados por quem chama, não copiados."""

        if existing is None:

            return fresh

        for name in fresh.__dataclass_fields__:

            if name in ("date", "is_final"):

                continue

            value = getattr(fresh, name)

            if value is not None:

                setattr(existing, name, value)

        return existing

    @staticmethod
    def poll_one(
        profile: str,
        repo: GarminHealthRepository | None = None,
        *,
        recovery_only: bool = False,
    ) -> None:
        """Puxa o retrato de saúde do atleta. `recovery_only=True` faz só a
        LEITURA DA MANHÃ (finaliza ontem + prontidão de hoje) — barato, roda
        num tick frequente; os scans caros (VO₂/body-context/previsão) ficam
        de fora e são cobertos pelo tick horário (`recovery_only=False`)."""

        repo = repo or GarminHealthRepository()

        runner = RunnerProfileRepository().load(profile)

        now_local = now_in(getattr(runner, "timezone", None))

        today = now_local.date()

        yesterday = (today - timedelta(days=1)).isoformat()

        today_iso = today.isoformat()

        # (1) FINALIZAR o dia FECHADO (ontem): puxa o dia inteiro UMA vez, quando
        # fecha, e marca is_final. Se já está finalizado, nem toca (imutável,
        # gentil com a API). Cobre também o registro que nasceu parcial como
        # "hoje" (is_final=False) — ao virar ontem, é reescrito completo.
        y_existing = repo.get(profile, yesterday)

        if y_existing is None or not y_existing.is_final:

            closed = GarminHealthSource.fetch(profile, yesterday)

            if closed.has_data:

                merged = GarminHealthPoller._merge(y_existing, closed)

                merged.is_final = True

                repo.upsert(profile, merged)

        # (2) LEITURA DA MANHÃ (hoje): o Garmin DATA o sono da noite pela manhã
        # em que ela TERMINA (a noite de domingo→segunda é "sono de segunda"),
        # e ele fica pronto na API POUCO DEPOIS de o atleta acordar — então a
        # leitura do corpo sai SAME-DAY, sem esperar o dia virar.
        #
        # O sinal-âncora é o SONO. O relógio sincroniza stress/SpO2/bateria-
        # corrente (e às vezes HRV) ANTES de o sono ser processado; parar no
        # primeiro sinal (has_recovery) dava "manhã capturada" cedo demais e
        # deixava o SONO cair pro dia seguinte — o atleta via a noite ANTERIOR
        # (o "domingo na segunda"). Por isso insistimos enquanto o sono ainda
        # não veio E ainda é de manhã: captura o sono no 1º tick após o relógio
        # sincronizar e então para (gentil com a API). Passado o corte, aceita
        # o que tem (o dia é finalizado completo amanhã, no passo (1)).
        t_existing = repo.get(profile, today_iso)

        morning_open = now_local.hour < _MORNING_SLEEP_CUTOFF_HOUR

        if t_existing is None or (
            t_existing.sleep_hours is None and morning_open
        ):

            fresh = GarminHealthSource.fetch(profile, today_iso)

            if fresh.has_data:

                merged = GarminHealthPoller._merge(t_existing, fresh)

                merged.is_final = False

                repo.upsert(profile, merged)

        # A leitura da manhã (passos 1 e 2) é barata — o gate por data/sono corta
        # a maioria dos pulls — e roda num tick FREQUENTE pra aparecer logo que o
        # relógio sincroniza. Os scans abaixo são CAROS (varrem vários dias na
        # API) e não urgentes: rodam no tick horário. Ver weekly_plan_scheduler.
        if recovery_only:

            return

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
