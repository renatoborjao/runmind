from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutedBlock:
    """Um bloco PRESCRITO (aquecimento/tiro/recuperação/desaquecimento/
    corrida contínua) pareado com o que foi EXECUTADO de verdade — usa as
    voltas rotuladas do Garmin, não splits genéricos por km."""

    kind: str

    label: str

    planned_distance_m: float | None
    planned_duration_sec: int | None

    pace_min: str | None
    pace_max: str | None

    executed_distance_m: float
    executed_duration_sec: float

    executed_pace: float | None  # min/km
    executed_hr: int | None

    # None = sem alvo de pace pra checar (ex.: aquecimento livre)
    within_target: bool | None = None


@dataclass(slots=True)
class BlockComparison:
    """Comparação bloco-a-bloco entre o treino prescrito (`planned.steps`)
    e o executado (voltas rotuladas do Garmin) — pareados na ordem
    prescrita, tolerante a voltas faltando/sobrando."""

    blocks: list[ExecutedBlock] = field(default_factory=list)

    # labels prescritos sem volta executada correspondente (ex.: atleta
    # parou antes de terminar a série)
    missing: list[str] = field(default_factory=list)

    # voltas executadas que sobraram sem par prescrito
    extra: int = 0
