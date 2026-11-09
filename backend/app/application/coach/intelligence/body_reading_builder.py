"""Costura a CARGA (camada 2) com a RECUPERAÇÃO (camada 1) numa leitura única
do corpo — a régua do Renato: a carga NUNCA é lida sozinha, sempre à luz da
recuperação. Rampa de carga COM recuperação boa = corpo absorvendo (não é
sobrecarga); rampa COM recuperação caindo = alerta de verdade.

Puro/determinístico: entrega o veredito PRONTO pra a IA narrar (a IA não
recalcula, igual à comparação bloco-a-bloco). Ver [[project_analise_corpo_garmin]]."""

import statistics
from datetime import date

from app.application.history.hr_zone_resolver import HrZoneResolver
from app.application.history.recovery_trend_analyzer import (
    RecoveryTrendAnalyzer,
)
from app.application.history.training_load_analyzer import (
    TrainingLoadAnalyzer,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    BodyReading,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_foot_sport
from app.domain.entities.training_load import (
    ACWR_OPTIMAL_MAX,
    LOAD_CAUTION,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
)
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# média de passos/dia a partir da qual a carga de vida FORA do treino pesa na
# recuperação (dia após dia muito em pé/andando cobra, mesmo sem treinar mais)
_HIGH_LIFE_LOAD_STEPS = 12000



class BodyReadingBuilder:

    @staticmethod
    def build(
        profile: str,
        reference_date: date | None = None,
    ) -> BodyReading:

        series = GarminHealthRepository().load(profile)

        runner = RunnerProfileRepository().load(profile)

        # intensidade da carga (v2) precisa de FC repouso (mediana da série de
        # saúde) + FC máx (idade via Tanaka); sem eles, o analisador cai no v1
        resting_hr = BodyReadingBuilder._resting_hr(series)


        # a CARGA (razão aguda/crônica = risco de lesão da CORRIDA: impacto,
        # tendão, osso) é só corrida/caminhada. Musculação/futebol/bike cansam,
        # mas o cansaço geral já aparece na RECUPERAÇÃO (HRV, FC repouso, sono) —
        # somar os minutos deles na carga inflava "pico" (João 27/09: a
        # musculação virou "sobrecarregado"). Somos coach de CORRIDA (Renato).
        # O cross-training segue no dossiê como contexto de cansaço.
        activities = [
            a for a in ActivityArchiveRepository().load_activities(profile)
            if is_foot_sport(a.sport)
        ]

        # FC máx da régua única de zonas (a do relógio, quando há) — a mesma do
        # gráfico/mensagem; Tanaka só quando não há régua. Ver [[HrZoneResolver]].
        zones = HrZoneResolver.resolve(runner, activities, resting_hr)

        max_hr = (
            zones.max_hr
            if zones is not None and zones.max_hr
            else BodyReadingBuilder._max_hr(getattr(runner, "age", None))
        )

        # PROVA recente: o taper que a antecede deflaciona a base crônica e o
        # ACWR vira um pico falso (pós-prova). Detecta do que o coach já sabia
        # (debrief) + rede do Strava, e a análise de carga desconta o taper.
        recent_race_date = BodyReadingBuilder._recent_race_date(
            profile, activities, reference_date
        )

        load = TrainingLoadAnalyzer.analyze(
            TrainingHistory(activities=activities),
            reference_date=reference_date,
            resting_hr=resting_hr,
            max_hr=max_hr,
            sex=getattr(runner, "sex", None),
            recent_race_date=recent_race_date,
            zones=zones,
        )

        recovery = RecoveryTrendAnalyzer.analyze(
            series, reference_date=reference_date
        )

        body_state = BodyReadingBuilder._verdict(load.status, recovery)

        # "carga alta E recuperação caindo" só é sobrecarga de treino se a carga veio ANTES da
        # queda (ou junto dela). Se a recuperação já vinha caindo quando a carga ainda era normal
        # ou leve (doença, sono, vida), a carga que subiu depois não foi a causa: é um sinal de
        # recuperação, não de sobrecarga — senão todo retorno de parada vira "sobrecarregado" e o
        # coach corta justo a semana em que o atleta volta (o dente de serra).
        alert_since = None

        alert_preceded = False

        if body_state in (BODY_STRAINED, BODY_RECOVERY_FLAG):

            alert_since, alert_preceded = BodyReadingBuilder._alert_preceded_load(
                series=series,
                activities=activities,
                reference_date=reference_date,
                resting_hr=resting_hr,
                max_hr=max_hr,
                sex=getattr(runner, "sex", None),
                recent_race_date=recent_race_date,
                zones=zones,
            )

            if alert_preceded and body_state == BODY_STRAINED:

                body_state = BODY_RECOVERY_FLAG

        limiter = BodyReadingBuilder._limiter(recovery)

        return BodyReading(
            load=load,
            recovery=recovery,
            body_state=body_state,
            limiter=limiter,
            alert_preceded_load=alert_preceded,
            alert_since=alert_since,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _alert_preceded_load(
        *, series, activities, reference_date, resting_hr, max_hr, sex, recent_race_date, zones,
    ):
        """(início do alerta, a recuperação começou a cair ANTES da carga subir?). Só afirma com o
        alerta mais antigo que a janela aguda (7 dias) e a carga DAQUELE dia lida como normal ou
        leve — qualquer dúvida (sem série, sem dado de carga) devolve False e o veredito fica como
        estava. Best-effort: nunca derruba a leitura."""

        try:

            from app.application.history.recovery_alert_run import RecoveryAlertRun
            from app.core.clock import today_local

            today = reference_date or today_local()

            since = RecoveryAlertRun.since(series, today)

            if since is None or (today - since).days < 7:

                return since, False

            earlier = TrainingLoadAnalyzer.analyze(
                TrainingHistory(activities=activities),
                reference_date=since,
                resting_hr=resting_hr,
                max_hr=max_hr,
                sex=sex,
                recent_race_date=recent_race_date,
                zones=zones,
            )

            # com pouco histórico a razão fica instável pra CIMA (divisor pequeno), nunca pra baixo:
            # uma razão baixa mesmo sem histórico suficiente é leitura segura de "carga leve"
            # (Renato em 29/10: 20 dias de histórico por causa da parada, razão 0,59)
            unknown_or_high = earlier.status in (LOAD_CAUTION, LOAD_HIGH) or (
                earlier.status == LOAD_INSUFFICIENT
                and (earlier.acwr is None or earlier.acwr > ACWR_OPTIMAL_MAX)
            )

            return since, not unknown_or_high

        except Exception as e:  # noqa: BLE001

            print(f"Alerta × carga (leitura de corpo) falhou: {e}")

            return None, False

    # ------------------------------------------------------------------

    @staticmethod
    def _recent_race_date(profile, activities, reference_date):
        """Data da última prova (na janela) — do que o coach já sabia (debrief)
        + rede do Strava. None sem prova. Best-effort: falhar aqui nunca derruba
        a leitura de corpo. Ver [[race_detector]]."""

        try:

            from app.application.history.race_detector import RaceDetector
            from app.core.clock import today_local
            from app.infrastructure.persistence.race_result_repository import (
                RaceResultRepository,
            )

            ref = reference_date or today_local()

            race = RaceDetector.most_recent(
                activities, ref, past_results=RaceResultRepository().load(profile)
            )

            return race.date if race else None

        except Exception as e:  # noqa: BLE001

            print(f"Detecção de prova (leitura de corpo) falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def _resting_hr(series) -> int | None:
        """FC de repouso do atleta = mediana dos valores da série de saúde
        (robusta a um dia atípico). None se não houver dado."""

        values = [h.resting_hr for h in series if h.resting_hr is not None]

        return round(statistics.median(values)) if values else None

    @staticmethod
    def _max_hr(age) -> int | None:
        """FC máxima estimada por Tanaka (208 − 0,7·idade), mais precisa que
        220−idade. Sem idade → None (carga cai no v1 por duração)."""

        if not age or age <= 0:

            return None

        return round(208 - 0.7 * age)

    @staticmethod
    def _verdict(load_status: str, recovery) -> str:
        """A régua central: cruza carga × recuperação."""

        # a definição de "recuperação piorando" é UMA só (a mesma que conta os
        # dias em alerta): ver RecoveryTrendAnalyzer.is_declining
        recovery_declining = RecoveryTrendAnalyzer.is_declining(recovery)

        # sem histórico de carga suficiente: veredito puxado pela recuperação
        if load_status == LOAD_INSUFFICIENT:

            return BODY_RECOVERY_FLAG if recovery_declining else BODY_BUILDING

        if recovery_declining:

            # carga subindo E corpo dando sinal de piora = alerta real
            if load_status in (LOAD_HIGH, LOAD_CAUTION):

                return BODY_STRAINED

            # carga ok/baixa mas recuperação caindo: o problema não é treino
            return BODY_RECOVERY_FLAG

        # recuperação OK a partir daqui
        if load_status in (LOAD_HIGH, LOAD_CAUTION):

            # rampou, MAS o corpo está absorvendo — não é sobrecarga
            return BODY_ABSORBING

        if load_status == LOAD_OPTIMAL:

            return BODY_BALANCED

        # LOAD_LIGHT / LOAD_DETRAINING: carga abaixo do normal dele e a
        # recuperação em dia — descansado, com espaço pra puxar
        return BODY_FRESH

    @staticmethod
    def _limiter(recovery) -> str | None:
        """O que mais merece atenção do atleta — o nó acionável. Sono primeiro
        (driver nº1 e o mais controlável)."""

        nights = recovery.nights_counted

        if recovery.sleep_avg_hours is not None and nights:

            enough_short = recovery.short_nights >= max(2, round(nights * 0.4))

            if recovery.sleep_avg_hours < 6.5 or enough_short:

                return "sono"

        if recovery.rhr_direction == FALLING:

            return "fc_repouso"

        if recovery.stress_avg is not None and recovery.stress_avg >= 40:

            return "stress"

        # carga de vida alta: o atleta não está descansando FORA do treino
        # (muito tempo em pé/andando) — nó real e acionável, mas de menor
        # urgência que sono/FC/stress, então vem por último.
        if (
            recovery.steps_avg is not None
            and recovery.steps_avg >= _HIGH_LIFE_LOAD_STEPS
        ):

            return "carga_vida"

        return None
