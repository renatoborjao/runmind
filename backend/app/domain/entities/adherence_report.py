from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# tendência da aderência ao longo do período analisado
ADHERENCE_RISING = "RISING"
ADHERENCE_STABLE = "STABLE"
ADHERENCE_FALLING = "FALLING"
ADHERENCE_INSUFFICIENT = "INSUFFICIENT_DATA"


@dataclass(slots=True)
class WeekAdherence:
    """Uma semana fechada: quantas sessões do plano viraram treino real, e
    o que ficou pra trás (dia e tipo) — a matéria-prima do padrão."""

    week_start: date

    planned: int

    done: int

    missed_days: list[str] = field(default_factory=list)

    missed_types: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:

        return self.done / self.planned if self.planned else 0.0


@dataclass(slots=True)
class MissedPattern:
    """O que mais escapa — um dia da semana ou um tipo de treino. `count` é
    quantas vezes ficou pra trás; `opportunities`, quantas vezes chegou a
    ser planejado (furar 3 de 3 quintas é MUITO diferente de 3 de 8)."""

    label: str

    count: int

    opportunities: int


@dataclass(slots=True)
class AdherenceReport:
    """Aderência ao plano ao LONGO DO TEMPO (o resumo semanal já dizia
    quantos treinos saíram na semana; isto conta a história de várias).

    Serve a dois consumidores: o atleta (série + o que ele vive furando) e
    a IA-treinadora, que pode reposicionar o dia/tipo em vez de represcrever
    o mesmo treino que nunca acontece. Padrão só é afirmado quando repete —
    furar uma vez é vida, não padrão."""

    weeks: list[WeekAdherence] = field(default_factory=list)

    # fração cumprida no período inteiro; None sem nenhuma semana com plano
    rate: float | None = None

    trend: str = ADHERENCE_INSUFFICIENT

    missed_day: MissedPattern | None = None

    missed_type: MissedPattern | None = None

    @property
    def has_series(self) -> bool:
        """Duas semanas já contam uma história; uma só é o que o resumo
        semanal de hoje já mostra."""

        return len(self.weeks) >= 2
