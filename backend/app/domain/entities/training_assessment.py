from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TrainingAssessment:
    """
    Resultado da avaliação do atleta.

    Esse objeto resume o estado atual do corredor
    e será utilizado pelo Planner para montar os
    próximos treinos.
    """

    level: str

    current_weekly_volume: float

    recommended_weekly_volume: float

    consistency: float

    longest_run: float

    available_training_days: int

    goal: str

    observations: list[str] = field(default_factory=list)

    # Iniciante que deve começar correndo-caminhando (só caminha / alto
    # IMC): o planejador usa a trilha run/walk em vez de corrida contínua.
    run_walk: bool = False