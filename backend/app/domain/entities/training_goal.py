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

    priority: str = "A"

    @property
    def race_label(self) -> str:
        """Como CHAMAR a PROVA (distância), NUNCA a aspiração de fundo. `name`
        é o objetivo do atleta ("correr 21 km, buscar saúde...") e não deve
        rotular a prova — quem faz isso troca a prova de 10k pela meta de 21km
        (bug real do Renato). Distância oficial vira nome."""

        km = self.distance_km

        if abs(km - 42.195) < 0.5:

            return "maratona"

        if abs(km - 21.0975) < 0.6:

            return "meia maratona"

        if abs(km - round(km)) < 0.05:

            return f"{km:.0f} km"

        return f"{km:.1f} km"