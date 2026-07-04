from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.application.history.metrics_resolver import ROOKIE_WEEKLY_KM
from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_history import TrainingHistory


class TrainingAssessmentBuilder:

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> TrainingAssessment:

        weekly = WeeklyVolumeAnalyzer.analyze(history)

        current_weekly_volume = weekly["average_4_weeks"]

        longest = 0

        if history.longest_run:
            longest = history.longest_run.distance / 1000

        # Sem histórico: usa o volume autodeclarado no onboarding
        # (ou o piso de estreante), sem progressão na primeira
        # semana (conservador).
        if current_weekly_volume == 0:

            current_weekly_volume = (
                runner.initial_weekly_km or ROOKIE_WEEKLY_KM
            )

            recommended_weekly_volume = round(
                current_weekly_volume,
                1,
            )

            longest = longest or round(
                current_weekly_volume
                / max(runner.weekly_training_days, 1),
                1,
            )

        else:

            recommended_weekly_volume = round(
                current_weekly_volume * 1.08,
                1,
            )

        observations = []

        # Nível olha capacidade real, não só volume: quem já corre 12 km
        # não é iniciante mesmo com volume semanal moderado.
        if current_weekly_volume >= 45 or longest >= 18:
            level = "Advanced"

        elif current_weekly_volume >= 20 or longest >= 8:
            level = "Intermediate"

        else:
            level = "Beginner"

        observations.append(
            f"Volume médio (4 semanas): {current_weekly_volume:.1f} km."
        )

        observations.append(
            f"Melhor semana: {weekly['max_week']:.1f} km."
        )

        observations.append(
            f"Última semana: {weekly['last_week']:.1f} km."
        )

        return TrainingAssessment(

            level=level,

            current_weekly_volume=current_weekly_volume,

            recommended_weekly_volume=recommended_weekly_volume,

            consistency=ConsistencyCalculator.calculate(
                history,
                runner.weekly_training_days,
            ),

            longest_run=round(longest, 1),

            available_training_days=runner.weekly_training_days,

            goal=runner.goal,

            observations=observations,
        )