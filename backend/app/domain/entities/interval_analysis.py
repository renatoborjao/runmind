from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IntervalAnalysis:
    """Tiros detectados no stream segundo-a-segundo (velocidade + FC), o
    único dado que revela intervalado curto (ex.: 8x400m) que os splits
    por km borram. Traz a resposta de FC — subiu no tiro, caiu na pausa."""

    rep_count: int

    # pace médio dos tiros (min/km)
    avg_rep_pace: float

    # FC de pico média entre os tiros e FC média nas recuperações
    avg_peak_hr: int | None
    avg_recovery_hr: int | None

    # por tiro: {"distance_m", "pace", "peak_hr"}
    reps: list[dict] = field(default_factory=list)
