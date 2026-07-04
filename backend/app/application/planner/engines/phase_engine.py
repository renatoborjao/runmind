from datetime import date

from app.core.clock import today_local
from app.domain.entities.training_goal import TrainingGoal

BASE_THRESHOLD_WEEKS = 8

PEAK_THRESHOLD_WEEKS = 4

TAPER_THRESHOLD_WEEKS = 2


class PhaseEngine:
    """
    Fase do ciclo de treino, calculada pela distância até a prova alvo.

    Ancorada na prova: BASE (constrói base, >8sem) -> BUILD (qualidade,
    4-8sem) -> PICO (afiação, 2-4sem) -> TAPER (polimento, <2sem).

    Sem prova (ou prova já passada): BUILD — progressão contínua.
    """

    @staticmethod
    def execute(
        goal: TrainingGoal,
        reference_date: date | None = None,
    ) -> str:

        reference_date = reference_date or today_local()

        if goal.race_date is None or goal.race_date <= reference_date:

            return "BUILD"

        weeks_to_race = (
            goal.race_date - reference_date
        ).days / 7

        if weeks_to_race > BASE_THRESHOLD_WEEKS:

            return "BASE"

        if weeks_to_race < TAPER_THRESHOLD_WEEKS:

            return "TAPER"

        if weeks_to_race < PEAK_THRESHOLD_WEEKS:

            return "PEAK"

        return "BUILD"
