from datetime import date

from app.application.planner.engines.distribution_engine import DistributionEngine
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.engines.run_walk_engine import RunWalkEngine
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.strategy.session_composer import SessionComposer
from app.application.planner.strategy.training_strategy import TrainingStrategy
from app.application.workouts.generator import WorkoutGenerator
from app.domain.entities.runner_baseline import RunnerBaseline
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
        baseline: RunnerBaseline | None = None,
        target_volume: float | None = None,
    ) -> TrainingPlan:

        phase = PhaseEngine.execute(goal)

        running_days = DistributionEngine.execute(
            runner
        )

        if not running_days:

            raise Exception(
                "Corredor sem dias de treino preferidos."
            )

        # Iniciante que começa por corrida-caminhada: trilha própria
        # (caminhada + trote em intervalos, medida em tempo), sem volume
        # de corrida contínua nem periodização de prova.
        if assessment.run_walk:

            return TrainingPlan(
                athlete_name=runner.name,
                objective=goal.name,
                phase=phase,
                weekly_volume=0.0,
                running_days=running_days,
                week_start=week_start,
                sessions=RunWalkEngine.build(
                    running_days,
                    training_week,
                    runner,
                ),
                is_deload=False,
            )

        is_deload = (
            training_week % TrainingPlanner.DELOAD_EVERY == 0
            and phase in ("BASE", "BUILD")
        )

        # Track A: com retrato real (histórico ou declarado), o volume-alvo
        # é o da progressão e as distâncias saem ancoradas no que ele corre.
        anchored = (
            baseline is not None
            and baseline.weekly_km > 0
            and target_volume is not None
        )

        strategy = TrainingStrategy.build(
            assessment,
            phase,
            is_deload,
            base_volume=target_volume if anchored else None,
        )

        if anchored:

            sessions = TrainingPlanner._build_sessions_from_baseline(
                strategy,
                metrics,
                running_days,
                assessment.level,
                phase,
                baseline,
                runner.preferred_long_run_day,
            )

        else:

            sessions = TrainingPlanner._build_sessions(
                strategy,
                metrics,
                running_days,
                assessment.level,
                phase,
                runner.preferred_long_run_day,
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
        preferred_long_run_day: str | None = None,
    ) -> list:
        """Compõe a semana pelo SessionComposer (tipos por nível/fase e
        nº de dias) e distribui o volume: longão pela capacidade, o resto
        rateado entre as demais sessões por peso de tipo."""

        composed = SessionComposer.compose(
            level,
            phase,
            running_days,
            preferred_long_run_day,
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

    # Distância "natural" de cada tipo relativa à rodagem típica do atleta
    # (rodagem = 1.0). Preserva a FORMA real da semana; o conjunto é depois
    # escalado pra fechar no volume-alvo.
    _ANCHOR_FACTOR = {
        "EASY": 1.0,
        "RECOVERY": 0.7,
        "PROGRESSION": 0.9,
        "TEMPO": 0.9,
        "VO2": 0.9,
        "FARTLEK": 0.9,
    }

    # O longão pode ocupar até esta fração da semana (no volume baixo ele
    # é naturalmente grande; conforme o volume sobe, vira fração menor).
    _MAX_LONG_FRACTION = 0.75

    # Piso de uma corrida de apoio: o longão cede espaço pra cada dia
    # escolhido ter ao menos isso.
    _SUPPORT_FLOOR_KM = 2.0

    @staticmethod
    def _build_sessions_from_baseline(
        strategy: dict,
        metrics: RunnerMetrics,
        running_days: list[str],
        level: str,
        phase: str,
        baseline: RunnerBaseline,
        preferred_long_run_day: str | None = None,
    ) -> list:
        """Respeita os DIAS ESCOLHIDOS pelo atleta (todos entram) e mantém o
        LONGÃO o mais fiel possível ao real, cortando só o necessário pra
        sobrar um piso pras demais corridas. Conforme o volume sobe, o
        longão chega ao real e os apoios crescem."""

        composed = SessionComposer.compose(
            level,
            phase,
            running_days,
            preferred_long_run_day,
        )

        if not composed:

            return []

        weekly_volume = strategy["weekly_volume"]

        typical = baseline.typical_run_km or 1.0

        long_entry = next(
            (e for e in composed if e["type"] == "LONG_RUN"),
            None,
        )

        non_long = [e for e in composed if e["type"] != "LONG_RUN"]

        if long_entry is not None:

            # longão o mais próximo do real, deixando um piso pras outras
            room = (
                weekly_volume
                - len(non_long) * TrainingPlanner._SUPPORT_FLOOR_KM
            )

            long_km = min(
                baseline.longest_km or typical,
                weekly_volume * TrainingPlanner._MAX_LONG_FRACTION,
                room,
            )

            long_km = round(
                max(long_km, TrainingPlanner._SUPPORT_FLOOR_KM),
                1,
            )

            remaining = max(weekly_volume - long_km, 0.0)

        else:

            long_km = 0.0

            remaining = weekly_volume

        anchors = [
            typical * TrainingPlanner._ANCHOR_FACTOR.get(e["type"], 1.0)
            for e in non_long
        ]

        natural = sum(anchors) or 1.0

        scale = remaining / natural if non_long else 0.0

        sessions = []

        for entry in composed:

            if entry["type"] == "LONG_RUN":

                distance = long_km

            else:

                distance = (
                    typical
                    * TrainingPlanner._ANCHOR_FACTOR.get(entry["type"], 1.0)
                    * scale
                )

            session = WorkoutGenerator.generate(
                entry["type"],
                round(distance, 1),
            )

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