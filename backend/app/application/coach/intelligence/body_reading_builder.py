"""Costura a CARGA (camada 2) com a RECUPERAÇÃO (camada 1) numa leitura única
do corpo — a régua do Renato: a carga NUNCA é lida sozinha, sempre à luz da
recuperação. Rampa de carga COM recuperação boa = corpo absorvendo (não é
sobrecarga); rampa COM recuperação caindo = alerta de verdade.

Puro/determinístico: entrega o veredito PRONTO pra a IA narrar (a IA não
recalcula, igual à comparação bloco-a-bloco). Ver [[project_analise_corpo_garmin]]."""

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
    RISING,
    BodyReading,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_load import (
    LOAD_CAUTION,
    LOAD_DETRAINING,
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


class BodyReadingBuilder:

    @staticmethod
    def build(
        profile: str,
        reference_date: date | None = None,
    ) -> BodyReading:

        activities = ActivityArchiveRepository().load_activities(profile)

        load = TrainingLoadAnalyzer.analyze(
            TrainingHistory(activities=activities),
            reference_date=reference_date,
        )

        series = GarminHealthRepository().load(profile)

        recovery = RecoveryTrendAnalyzer.analyze(series)

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
    def _verdict(load_status: str, recovery) -> str:
        """A régua central: cruza carga × recuperação."""

        # recuperação vem do Garmin em direção-de-recuperação (RISING=melhora,
        # FALLING=piora); sem dado de recuperação, nada "caindo"
        recovery_declining = (
            recovery.hrv_direction == FALLING
            or recovery.rhr_direction == FALLING
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

        return None
