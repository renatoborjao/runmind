from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.workout_step import WorkoutStep


@dataclass(slots=True)
class PlannedSession:

    day: str

    workout_type: str

    objective: str

    planned_distance_km: float | None

    planned_duration_minutes: int | None

    target_pace_min: str | None

    target_pace_max: str | None

    notes: str = ""

    adjusted: bool = False

    adjustment_reason: str | None = None

    # Estrutura de intervalos para run/walk (caminhada/trote). Quando
    # presente, a sessão é medida em tempo, não em km. Ex:
    #   {"warmup_min": 5, "trot_sec": 60, "walk_sec": 180,
    #    "reps": 6, "cooldown_min": 5}
    intervals: dict | None = None

    # Modalidade da sessão: "run" (corrida), "walk" (caminhada) ou
    # "run_walk" (corrida-caminhada, iniciante). O plano é SÓ de
    # corrida/caminhada — musculação e outras atividades não entram.
    kind: str = "run"

    # Riqueza do plano gerado pela IA-treinadora: como executar (blocos,
    # séries, strides, fechamento progressivo) e o porquê do treino.
    structure: str = ""

    purpose: str = ""

    # Passos ESTRUTURADOS do treino (aquecimento, séries, recuperação,
    # desaquecimento...) — fonte de verdade pra montar o treino guiado no
    # Garmin. Vazio = cai no fallback (distância+pace num passo só).
    steps: list[WorkoutStep] = field(default_factory=list)