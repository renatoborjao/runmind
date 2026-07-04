from datetime import date

from app.application.planner.engines.distribution_engine import DistributionEngine
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.strategy.session_composer import SessionComposer
from app.application.planner.strategy.training_strategy import TrainingStrategy
from app.application.workouts.generator import WorkoutGenerator
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan


class TrainingPlanner:

    # Ciclo 3:1 — a cada 4ª semana de treino, deload (só em BASE/BUILD;
    # PICO e TAPER já são reduzidos por fase).
    DELOAD_EVERY = 4

    @staticmethod
    def generate(
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        goal: TrainingGoal,
        metrics: RunnerMetrics,
        week_start: date,
        training_week: int = 1,
    ) -> TrainingPlan:

        phase = PhaseEngine.execute(goal)

        is_deload = (
            training_week % TrainingPlanner.DELOAD_EVERY == 0
            and phase in ("BASE", "BUILD")
        )

        strategy = TrainingStrategy.build(
            assessment,
            phase,
            is_deload,
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
            assessment.level,
            phase,
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

            is_deload=is_deload,
        )

    # Peso relativo de distância por tipo (rodagem = referência). Divide
    # o volume da semana (fora o longão) entre as sessões: qualidade e
    # regenerativo são mais curtos que uma rodagem.
    _DISTANCE_WEIGHT = {
        "EASY": 1.0,
        "RECOVERY": 0.6,
        "PROGRESSION": 0.9,
        "TEMPO": 0.85,
        "VO2": 0.8,
        "FARTLEK": 0.85,
    }

    @staticmethod
    def _build_sessions(
        strategy: dict,
        metrics: RunnerMetrics,
        running_days: list[str],
        level: str,
        phase: str,
    ) -> list:
        """Compõe a semana pelo SessionComposer (tipos por nível/fase e
        nº de dias) e distribui o volume: longão pela capacidade, o resto
        rateado entre as demais sessões por peso de tipo."""

        composed = SessionComposer.compose(
            level,
            phase,
            running_days,
        )

        if not composed:

            return []

        weekly_volume = strategy["weekly_volume"]

        long_km = strategy["long_run"]

        has_long = any(c["type"] == "LONG_RUN" for c in composed)

        remaining = weekly_volume - (long_km if has_long else 0)

        remaining = max(remaining, 0.0)

        total_weight = sum(
            TrainingPlanner._DISTANCE_WEIGHT.get(c["type"], 1.0)
            for c in composed
            if c["type"] != "LONG_RUN"
        ) or 1.0

        sessions = []

        for entry in composed:

            code = entry["type"]

            if code == "LONG_RUN":

                distance = long_km

            else:

                weight = TrainingPlanner._DISTANCE_WEIGHT.get(code, 1.0)

                distance = remaining * weight / total_weight

            session = WorkoutGenerator.generate(code, distance)

            session.day = entry["day"]

            TrainingPlanner._apply_pace(session, metrics)

            sessions.append(session)

        return sessions

    @staticmethod
    def _apply_pace(
        session,
        metrics: RunnerMetrics,
    ) -> None:
        """Faixa de pace por tipo de treino, a partir das métricas."""

        easy_min = PaceFormatter.format(metrics.easy_pace_min)

        easy_max = PaceFormatter.format(metrics.easy_pace_max)

        threshold = PaceFormatter.format(metrics.threshold_pace)

        vo2 = PaceFormatter.format(metrics.vo2_pace)

        code = session.workout_type

        if code == "RECOVERY":

            session.target_pace_min = easy_max

            session.target_pace_max = PaceFormatter.format(
                metrics.easy_pace_max + 0.5,
            )

        elif code == "PROGRESSION":

            # começa leve, termina no limiar
            session.target_pace_min = easy_max

            session.target_pace_max = threshold

        elif code == "TEMPO":

            # ritmo de limiar, alvo único
            session.target_pace_min = threshold

            session.target_pace_max = threshold

        elif code == "VO2":

            # alvo único nos tiros
            session.target_pace_min = vo2

            session.target_pace_max = vo2

        elif code == "FARTLEK":

            # varia livre entre leve e forte
            session.target_pace_min = easy_max

            session.target_pace_max = vo2

        else:

            # EASY e LONG_RUN: faixa confortável
            session.target_pace_min = easy_min

            session.target_pace_max = easy_max