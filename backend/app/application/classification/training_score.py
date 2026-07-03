from dataclasses import dataclass

from app.application.classification.workout_type import (
    WorkoutType,
)


@dataclass(slots=True)
class TrainingScore:

    workout: WorkoutType

    score: int = 0

    reasons: list[str] | None = None

    def __post_init__(self):

        if self.reasons is None:

            self.reasons = []

    def add(
        self,
        points: int,
        reason: str,
    ):

        self.score += points

        self.reasons.append(reason)