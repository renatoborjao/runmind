from dataclasses import asdict, dataclass


@dataclass(slots=True)
class DailyHealth:
    """Retrato diário do CORPO do atleta, do Garmin — a matéria-prima da
    análise de recuperação/prontidão/carga (camada 1: só ingere e guarda,
    sem IA).

    DUAS CAMADAS de propósito, TODAS opcionais (o que vem preenchido depende
    do relógio):

    - Sinais que a própria GARMIN calcula (só nos relógios melhores, tipo
      FR265/965): readiness_score/level, training_status/load_balance,
      hrv_status, sleep_score. Quando vêm, MANDAM (a leitura na camada 3
      prefere o número da Garmin a derivar por conta).

    - PRIMITIVOS (qualquer relógio com sono/FC): horas de sono e estágios,
      HRV cru, stress, body battery, FC de repouso, VO2max. É com eles que a
      gente monta a própria prontidão quando o relógio não a calcula (ex.: o
      FR165, que deixa readiness/training_status vazios).

    Nada é obrigatório: relógio novo ainda sem baseline de HRV, device sem
    tal métrica, dia sem sono medido — tudo vira None, nunca quebra.
    """

    date: str  # dia que as métricas descrevem (YYYY-MM-DD, local do atleta)

    # -- sinais computados pela Garmin (relógios melhores; None nos básicos) --
    readiness_score: int | None = None
    readiness_level: str | None = None
    training_status: str | None = None
    training_load_balance: str | None = None
    hrv_status: str | None = None
    sleep_score: int | None = None

    # -- primitivos (presentes em qualquer relógio com sono/FC) --
    sleep_hours: float | None = None
    deep_sleep_hours: float | None = None
    rem_sleep_hours: float | None = None
    light_sleep_hours: float | None = None
    awake_hours: float | None = None
    hrv_last_night: int | None = None
    hrv_weekly_avg: int | None = None
    stress_avg: int | None = None
    stress_max: int | None = None
    body_battery_change: int | None = None
    resting_hr: int | None = None
    vo2max: float | None = None

    # -- carga de VIDA (esforço FORA do treino no dia; contexto de recuperação:
    #    dia parado recupera, dia de 15k passos + faxina não) --
    steps: int | None = None
    steps_goal: int | None = None
    active_calories: int | None = None
    intensity_minutes_moderate: int | None = None
    intensity_minutes_vigorous: int | None = None
    intensity_minutes_goal: int | None = None

    # -- body battery ao longo do dia (o saldo da noite já é body_battery_change;
    #    estes contam o TANQUE: com quanto acordou, pico, vale, agora) --
    body_battery_most_recent: int | None = None
    body_battery_at_wake: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None

    # -- respiração (rpm): a do SONO é sinal de recuperação (sobe com stress/
    #    álcool/doença); vigília e pico dão contexto --
    respiration_sleep_avg: float | None = None
    respiration_waking_avg: float | None = None
    respiration_high: float | None = None
    respiration_low: float | None = None

    # -- SpO2 (%): saturação; queda no sono = altitude/qualidade ruim/indício de
    #    algo errado (nem todo relógio mede — vira None sem quebrar) --
    spo2_avg: int | None = None
    spo2_sleep_avg: int | None = None
    spo2_low: int | None = None

    @property
    def has_data(self) -> bool:
        """True se o dia trouxe QUALQUER métrica de verdade. Um dia todo None
        (relógio não usado, ou antes de o atleta ter o Garmin) não vale a pena
        guardar — o backfill usa isso pra parar ao chegar antes do relógio."""

        return any(
            v is not None
            for v in (
                self.sleep_hours,
                self.sleep_score,
                self.hrv_last_night,
                self.stress_avg,
                self.resting_hr,
                self.vo2max,
                self.readiness_score,
            )
        )

    def to_dict(self) -> dict:

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DailyHealth":
        """Reconstrói tolerando chaves novas/ausentes — o arquivo persistido
        pode ter sido escrito por uma versão com campos a mais ou a menos."""

        fields = cls.__dataclass_fields__

        return cls(**{k: v for k, v in data.items() if k in fields})
