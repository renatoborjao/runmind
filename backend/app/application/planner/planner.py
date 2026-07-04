from datetime import date

from app.application.planner.engines.distribution_engine import DistributionEngine
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.strategy.training_strategy import TrainingStrategy
from app.application.workouts.generator import WorkoutGenerator
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan


class TrainingPlanner:

    @staticmethod
    def generate(
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        goal: TrainingGoal,
        metrics: RunnerMetrics,
        week_start: date,
    ) -> TrainingPlan:

        phase = PhaseEngine.execute(goal)

        strategy = TrainingStrategy.build(
            assessment,
            phase,
        )

        running_days = DistributionEngine.execute(
            runner
        )

        if not running_days:

            raise Exception(
                "Corredor sem dias de treino preferidos."
            )

        sessions = TrainingPlanner._build_sessions(
            strategy,
            metrics,
            running_days,
        )

        return TrainingPlan(

            athlete_name=runner.name,

            objective=goal.name,

            phase=phase,

            weekly_volume=strategy[
                "weekly_volume"
            ],

            running_days=running_days,

            week_start=week_start,

            sessions=sessions,
        )

    @staticmethod
    def _build_sessions(
        strategy: dict,
        metrics: RunnerMetrics,
        running_days: list[str],
    ) -> list:
        """Sessões conforme a quantidade de dias disponíveis:
        1 dia = rodagem única com o volume da semana;
        2 dias = rodagem leve + longão;
        3+ dias = rodagem leve + VO2 + longão."""

        easy_pace_min = PaceFormatter.format(
            metrics.easy_pace_min,
        )

        easy_pace_max = PaceFormatter.format(
            metrics.easy_pace_max,
        )

        if len(running_days) == 1:

            easy = WorkoutGenerator.generate_easy(
                strategy["weekly_volume"]
            )

            easy.day = running_days[0]

            easy.target_pace_min = easy_pace_min

            easy.target_pace_max = easy_pace_max

            return [easy]

        if len(running_days) == 2:

            easy = WorkoutGenerator.generate_easy(
                round(
                    strategy["easy_run"]
                    + strategy["quality_run"],
                    1,
                )
            )

            long = WorkoutGenerator.generate_long(
                strategy["long_run"]
            )

            easy.day = running_days[0]

            long.day = running_days[1]

            easy.target_pace_min = easy_pace_min

            easy.target_pace_max = easy_pace_max

            long.target_pace_min = easy_pace_min

            long.target_pace_max = easy_pace_max

            return [easy, long]

        easy = WorkoutGenerator.generate_easy(
            strategy["easy_run"]
        )

        quality = TrainingPlanner._build_quality_session(
            strategy,
            metrics,
            easy_pace_min,
            easy_pace_max,
        )

        long = WorkoutGenerator.generate_long(
            strategy["long_run"]
        )

        easy.day = running_days[0]

        quality.day = running_days[1]

        long.day = running_days[2]

        # Rodagem leve: faixa de pace confortável.
        easy.target_pace_min = easy_pace_min

        easy.target_pace_max = easy_pace_max

        # Longão: mesma faixa confortável da rodagem leve.
        long.target_pace_min = easy_pace_min

        long.target_pace_max = easy_pace_max

        return [easy, quality, long]

    @staticmethod
    def _build_quality_session(
        strategy: dict,
        metrics: RunnerMetrics,
        easy_pace_min: str,
        easy_pace_max: str,
    ):
        """VO2 (intervalado) para quem tem base; progressivo para
        iniciante — a estratégia decide via quality_type."""

        distance = strategy["quality_run"]

        if strategy["quality_type"] == "PROGRESSION":

            progression = WorkoutGenerator.generate_progression(
                distance
            )

            # começa leve, termina no limiar
            progression.target_pace_min = easy_pace_max

            progression.target_pace_max = PaceFormatter.format(
                metrics.threshold_pace,
            )

            return progression

        vo2 = WorkoutGenerator.generate_vo2(distance)

        # VO2: alvo único de pace nos tiros.
        vo2.target_pace_min = PaceFormatter.format(
            metrics.vo2_pace,
        )

        vo2.target_pace_max = vo2.target_pace_min

        return vo2