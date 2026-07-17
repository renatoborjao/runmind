from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class TrainingGoal:

    name: str

    distance_km: float

    target_time: str | None

    # None = atleta sem prova alvo (progressão contínua)
    race_date: date | None

    # True quando o atleta declarou uma distância de prova real (target_race
    # no perfil) — independente de ter data marcada ou não. Diferente de
    # "tem prova com CONTAGEM REGRESSIVA" (isso exige race_date futuro);
    # usado por features que só precisam saber se a meta é uma distância de
    # verdade, não o default de 10km de quem só quer saúde.
    has_declared_distance: bool = False

    priority: str = "A"