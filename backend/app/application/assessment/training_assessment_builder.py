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

        no_history = current_weekly_volume == 0

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

        run_walk = TrainingAssessmentBuilder._needs_run_walk(
            runner,
            level,
            no_history,
        )

        if run_walk:

            observations.append(
                "Início por corrida-caminhada (run/walk)."
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

            run_walk=run_walk,
        )

    # IMC a partir do qual (sem histórico de corrida) o início seguro é
    # run/walk, mesmo sem o atleta se declarar caminhante — proteção
    # articular para iniciante de alto peso.
    RUN_WALK_BMI = 30.0

    @staticmethod
    def _needs_run_walk(
        runner: RunnerProfile,
        level: str,
        no_history: bool,
    ) -> bool:
        """Só para iniciante sem histórico: começa run/walk quando o
        atleta só caminha / faz trote-caminhada, ou quando o IMC é alto."""

        if not (no_history and level == "Beginner"):

            return False

        if runner.mobility in ("walker", "run_walker"):

            return True

        bmi = TrainingAssessmentBuilder._bmi(runner)

        return bmi >= TrainingAssessmentBuilder.RUN_WALK_BMI

    @staticmethod
    def _bmi(runner: RunnerProfile) -> float:

        if not runner.height:

            return 0.0

        return runner.weight / (runner.height ** 2)