from dataclasses import dataclass

from app.application.classification.workout_type import (
    WorkoutType,
)


@dataclass(slots=True)
class TrainingClassification:

    workout_type: WorkoutType

    intensity: str

    estimated_zone: str

    confidence: float

    reasons: list[str]