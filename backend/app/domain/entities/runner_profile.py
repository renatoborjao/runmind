from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class RunnerProfile:

    id: str

    name: str

    age: int

    weight: float

    height: float

    phone: str

    goal: str

    weekly_training_days: int

    preferred_running_days: list[str] = field(
        default_factory=list
    )

    strength_training_days: list[str] = field(
        default_factory=list
    )

    target_race: str | None = None

    target_time: str | None = None

    # ID do atleta no Strava.
    # Será utilizado pelo webhook para identificar
    # automaticamente o corredor.
    strava_athlete_id: int | None = None

    injuries: list[str] = field(
        default_factory=list
    )