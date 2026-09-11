from dataclasses import dataclass

from app.domain.entities.training_load import TrainingLoad

# direção de uma métrica ao longo dos dias
RISING = "rising"
FALLING = "falling"
STABLE = "stable"

# estado do corpo = carga LIDA À LUZ da recuperação (nunca a carga isolada)
BODY_STRAINED = "STRAINED"          # carga alta E recuperação caindo → alerta real
BODY_RECOVERY_FLAG = "RECOVERY_FLAG"  # carga ok/baixa mas recuperação caindo
BODY_ABSORBING = "ABSORBING"        # rampa de carga MAS corpo absorvendo bem
BODY_BALANCED = "BALANCED"          # carga ótima + recuperação ok
BODY_FRESH = "FRESH"                # carga baixa + recuperado → espaço pra puxar
BODY_BUILDING = "BUILDING"          # ainda sem histórico de carga pra veredito


@dataclass(slots=True)
class RecoveryTrend:
    """Tendência dos sinais de recuperação nos últimos dias (do Garmin)."""

    hrv_recent: float | None = None
    hrv_direction: str = STABLE          # subir é bom
    rhr_recent: int | None = None
    rhr_direction: str = STABLE          # cair é bom (FALLING = melhorando)
    sleep_avg_hours: float | None = None
    short_nights: int = 0                # noites < 6h no período
    nights_counted: int = 0
    stress_avg: int | None = None
    body_battery_recent: int | None = None
    vo2max: float | None = None
    days_covered: int = 0

    # -- tier-2: contexto de recuperação além dos marcadores de ouro --

    # body battery AO ACORDAR = o tanque com que o atleta começou o dia. Nos
    # relógios que não computam prontidão (FR165), é o proxy mais próximo dela.
    # O que pesa é o NÍVEL absoluto (acordar no vermelho = não recarregou); a
    # direção é contexto. Acordar em 91 com leve queda NÃO é alerta.
    body_battery_wake: int | None = None
    body_battery_wake_direction: str = STABLE   # acordar mais carregado é bom

    # respiração no SONO (rpm): sobe com stress/álcool/doença. Sinal narrado,
    # NÃO dirige o veredito (subir pode ser gripe, não treino).
    respiration_sleep: float | None = None
    respiration_direction: str = STABLE          # subir é PIOR (POV recuperação)

    # SpO2 MÉDIA no sono (%): a saturação SUSTENTADA da noite. Só narrada quando
    # baixa de verdade (não o vale de 1 noite, que engana); nunca é conselho
    # médico. Um mínimo transitório caindo a 86% é normal — a média conta.
    spo2_sleep_avg: int | None = None

    # carga de VIDA (esforço FORA do treino): recuperação não é só o que você
    # treina — dia de 14k passos + faxina também cobra. Contexto/limitador.
    steps_avg: int | None = None
    active_calories_avg: int | None = None
    intensity_minutes_avg: int | None = None     # (moderada + 2×vigorosa)/dia

    # Números que a PRÓPRIA Garmin computa (só relógios melhores; None no FR165).
    # Quando vêm, MANDAM — a leitura mostra/prefere o número do relógio a
    # derivar por conta. Ver [[project_analise_corpo_garmin]].
    sleep_score: int | None = None
    readiness_score: int | None = None
    readiness_level: str | None = None
    training_status: str | None = None
    hrv_status: str | None = None

    @property
    def has_data(self) -> bool:

        return self.days_covered > 0


@dataclass(slots=True)
class BodyReading:
    """Leitura do corpo: carga (camada 2) + recuperação (camada 1) costuradas
    num veredito ÚNICO — a carga sempre interpretada à luz da recuperação,
    nunca sozinha. É o fato pronto que a IA narra (camada 3)."""

    load: TrainingLoad
    recovery: RecoveryTrend
    body_state: str
    limiter: str | None = None   # o que mais merece atenção (ex.: "sono")
