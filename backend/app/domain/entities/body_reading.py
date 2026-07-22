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
