import re
from datetime import date

from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal

DEFAULT_DISTANCE_KM = 10.0


class BuildTrainingGoal:
    """Fonte única do TrainingGoal a partir do perfil do atleta —
    antes cada módulo montava o goal na mão (com race_date=None e
    distância fixa)."""

    @staticmethod
    def execute(
        runner: RunnerProfile,
    ) -> TrainingGoal:

        return TrainingGoal(
            name=runner.goal,
            distance_km=BuildTrainingGoal._distance_km(
                runner.target_race,
            ),
            target_time=runner.target_time,
            race_date=BuildTrainingGoal._race_date(
                runner.race_date,
            ),
        )

    @staticmethod
    def _distance_km(
        target_race: str | None,
    ) -> float:
        """"10 km" -> 10.0, "21k" -> 21.0, "5,5 km" -> 5.5."""

        if not target_race:

            return DEFAULT_DISTANCE_KM

        match = re.search(
            r"(\d+(?:[.,]\d+)?)",
            target_race,
        )

        if not match:

            return DEFAULT_DISTANCE_KM

        return float(match.group(1).replace(",", "."))

    @staticmethod
    def _race_date(
        race_date: str | None,
    ) -> date | None:

        if not race_date:

            return None

        try:

            return date.fromisoformat(race_date)

        except ValueError:

            return None
