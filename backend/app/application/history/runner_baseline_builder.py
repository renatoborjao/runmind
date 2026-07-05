from statistics import median

from app.application.history.weekly_buckets import group_by_week
from app.application.history.weekly_volume_analyzer import (
    WeeklyVolumeAnalyzer,
)
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory

_EMPTY = RunnerBaseline(
    has_history=False,
    weekly_km=0.0,
    last_week_km=0.0,
    max_week_km=0.0,
    runs_per_week=0.0,
    typical_run_km=0.0,
    longest_km=0.0,
    trend="estável",
)

# quantas semanas recentes definem a frequência real
FREQUENCY_WINDOW_WEEKS = 4

# banda morta da tendência: variação abaixo disso é "estável"
TREND_BAND = 0.10


class RunnerBaselineBuilder:
    """Lê o histórico e devolve o retrato real do corredor. Read-only,
    determinístico — mesma base de treino, mesmo retrato."""

    @staticmethod
    def build(
        history: TrainingHistory,
        runner: RunnerProfile | None = None,
    ) -> RunnerBaseline:

        activities = history.activities

        # Sem histórico do Strava: usa o retrato DECLARADO no onboarding
        # (já corre X km/semana em Y dias) — mesma lógica de evolução.
        if not activities:

            return RunnerBaselineBuilder._declared(runner)

        weekly = WeeklyVolumeAnalyzer.analyze(history)

        distances_km = [
            activity.distance / 1000 for activity in activities
        ]

        longest_km = (
            round(history.longest_run.distance / 1000, 1)
            if history.longest_run
            else 0.0
        )

        return RunnerBaseline(
            has_history=True,
            weekly_km=weekly["average_4_weeks"],
            last_week_km=weekly["last_week"],
            max_week_km=weekly["max_week"],
            runs_per_week=RunnerBaselineBuilder._runs_per_week(history),
            typical_run_km=round(median(distances_km), 1),
            longest_km=longest_km,
            trend=RunnerBaselineBuilder._trend(history),
        )

    @staticmethod
    def _declared(runner: RunnerProfile | None) -> RunnerBaseline:
        """Retrato inicial de quem declarou correr mas ainda não tem Strava:
        volume/dias autodeclarados viram o ponto de partida da evolução."""

        if runner is None or not runner.initial_weekly_km:

            return _EMPTY

        weekly = round(runner.initial_weekly_km, 1)

        days = max(runner.weekly_training_days, 1)

        typical = round(weekly / days, 1)

        return RunnerBaseline(
            has_history=False,
            weekly_km=weekly,
            last_week_km=weekly,
            max_week_km=weekly,
            runs_per_week=float(days),
            typical_run_km=typical,
            longest_km=typical,
            trend="estável",
        )

    @staticmethod
    def _runs_per_week(history: TrainingHistory) -> float:
        """Frequência real: média de corridas por semana ATIVA nas últimas
        semanas (semana sem treino não conta — não é 'ele treina 0x')."""

        buckets = group_by_week(history.activities)

        recent_keys = sorted(buckets)[-FREQUENCY_WINDOW_WEEKS:]

        counts = [len(buckets[key]) for key in recent_keys]

        if not counts:

            return 0.0

        return round(sum(counts) / len(counts), 1)

    @staticmethod
    def _trend(history: TrainingHistory) -> str:
        """Compara o volume das 2 semanas recentes com as 2 anteriores —
        evita o ruído de olhar só a última (que pode estar pela metade)."""

        buckets = group_by_week(history.activities)

        volumes = [
            sum(a.distance for a in buckets[key]) / 1000
            for key in sorted(buckets)
        ]

        if len(volumes) < 4:

            return "estável"

        recent = sum(volumes[-2:]) / 2

        prior = sum(volumes[-4:-2]) / 2

        if prior <= 0:

            return "estável"

        change = (recent - prior) / prior

        if change > TREND_BAND:

            return "subindo"

        if change < -TREND_BAND:

            return "caindo"

        return "estável"
