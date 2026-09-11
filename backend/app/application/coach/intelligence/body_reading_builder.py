"""Costura a CARGA (camada 2) com a RECUPERAÇÃO (camada 1) numa leitura única
do corpo — a régua do Renato: a carga NUNCA é lida sozinha, sempre à luz da
recuperação. Rampa de carga COM recuperação boa = corpo absorvendo (não é
sobrecarga); rampa COM recuperação caindo = alerta de verdade.

Puro/determinístico: entrega o veredito PRONTO pra a IA narrar (a IA não
recalcula, igual à comparação bloco-a-bloco). Ver [[project_analise_corpo_garmin]]."""

import statistics
from datetime import date

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
from app.domain.entities.training_load import (
    LOAD_CAUTION,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
)
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.cross_training_repository import (
    CrossTrainingRepository,
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

# body battery ao acordar abaixo disto = acordou "no vermelho" (não recarregou)
# — aí sim é sinal de recuperação ruim. Acordar cheio (mesmo caindo de leve) não.
_LOW_WAKE_BATTERY = 30


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

        max_hr = BodyReadingBuilder._max_hr(getattr(runner, "age", None))

        # o corpo sente TODO o estresse: a carga soma a corrida (arquivo) COM o
        # cross-training do Garmin (musculação/natação/Hyrox). Isso NUNCA entra
        # na leitura/plano/chat de corrida — só no contador do corpo. Ver
        # [[project_analise_corpo_garmin]].
        activities = (
            ActivityArchiveRepository().load_activities(profile)
            + CrossTrainingRepository().load_activities(profile)
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
        )

        recovery = RecoveryTrendAnalyzer.analyze(
            series, reference_date=reference_date
        )

        body_state = BodyReadingBuilder._verdict(load.status, recovery)

        limiter = BodyReadingBuilder._limiter(recovery)

        return BodyReading(
            load=load,
            recovery=recovery,
            body_state=body_state,
            limiter=limiter,
        )

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

        # recuperação vem do Garmin em direção-de-recuperação (RISING=melhora,
        # FALLING=piora); sem dado de recuperação, nada "caindo". Marcadores de
        # ouro: HRV e FC de repouso pela DIREÇÃO. Body battery entra pelo NÍVEL
        # absoluto (acordar no vermelho = não recarregou) — nunca pela direção
        # com tanque cheio (acordar em 91 caindo de leve não é alerta).
        waking_drained = (
            recovery.body_battery_wake is not None
            and recovery.body_battery_wake < _LOW_WAKE_BATTERY
        )

        recovery_declining = (
            recovery.hrv_direction == FALLING
            or recovery.rhr_direction == FALLING
            or waking_drained
        )

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

        # LOAD_DETRAINING
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
