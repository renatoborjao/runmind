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
                runner.goal,
            ),
            target_time=runner.target_time,
            race_date=BuildTrainingGoal._race_date(
                runner.race_date,
            ),
        )

    @staticmethod
    def _distance_km(
        target_race: str | None,
        goal_text: str | None = None,
    ) -> float:
        """"10 km" -> 10.0, "21k" -> 21.0, "5,5 km" -> 5.5. Provas nomeadas
        sem número ("meia maratona", "maratona") viram a distância oficial.

        Sem prova concreta (`target_race`), cai no OBJETIVO de fundo (`goal_text`,
        ex.: "correr 21 km com saúde" -> 21) — assim, quando a prova é cumprida
        e o alvo concreto é aposentado, a distância segue o objetivo do atleta,
        não o default. Ver [[project_multiplos_objetivos]]."""

        distance = BuildTrainingGoal._parse_distance(target_race)

        if distance is not None:

            return distance

        # sem prova concreta: o objetivo de fundo manda (senão, o default)
        from_goal = BuildTrainingGoal._parse_distance(goal_text)

        return from_goal if from_goal is not None else DEFAULT_DISTANCE_KM

    @staticmethod
    def _parse_distance(text: str | None) -> float | None:
        """Distância em km a partir de um texto livre, ou None se não houver
        pista. "10 km"->10; "meia maratona"->21.0975; "maratona"->42.195."""

        if not text:

            return None

        lowered = text.lower()

        # nomeadas sem número explícito (antes do regex, que não acha dígito)
        if "meia" in lowered and "marat" in lowered:

            return 21.0975

        match = re.search(
            r"(\d+(?:[.,]\d+)?)",
            text,
        )

        if match:

            return float(match.group(1).replace(",", "."))

        if "marat" in lowered:

            return 42.195

        return None

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
