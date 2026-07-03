from app.application.history.runner_metrics import RunnerMetricsBuilder
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory

# Mesmos offsets do RunnerMetricsBuilder (derivação por pace médio).
EASY_MIN_OFFSET = -0.25
EASY_MAX_OFFSET = 0.35
THRESHOLD_OFFSET = -0.60
VO2_OFFSET = -1.10

# Defaults conservadores de estreante (nunca correu / não informou pace).
ROOKIE_PACE = 8.0  # min/km
ROOKIE_WEEKLY_KM = 6.0
ROOKIE_MAX_LONG_RUN = 3.0


class MetricsResolver:
    """Métricas do corredor com ou sem histórico:

    1. histórico com paces -> RunnerMetricsBuilder (dados reais);
    2. sem histórico, com pace/volume autodeclarados no onboarding;
    3. sem nada -> defaults conservadores de estreante.

    Conforme os treinos do Strava chegam, o caminho 1 assume sozinho.
    """

    @staticmethod
    def resolve(
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> RunnerMetrics:

        has_paces = any(
            activity.average_speed > 0
            for activity in history.activities
        )

        if has_paces:

            return RunnerMetricsBuilder.build(history)

        pace = runner.initial_pace_min_km or ROOKIE_PACE

        weekly_km = runner.initial_weekly_km or ROOKIE_WEEKLY_KM

        return MetricsResolver._from_pace(pace, weekly_km)

    @staticmethod
    def _from_pace(
        pace: float,
        weekly_km: float,
    ) -> RunnerMetrics:

        return RunnerMetrics(

            easy_pace_min=round(pace + EASY_MIN_OFFSET, 2),

            easy_pace_max=round(pace + EASY_MAX_OFFSET, 2),

            threshold_pace=round(pace + THRESHOLD_OFFSET, 2),

            vo2_pace=round(pace + VO2_OFFSET, 2),

            average_hr=0,

            max_long_run=max(
                round(weekly_km * 0.35, 1),
                ROOKIE_MAX_LONG_RUN,
            ),

            weekly_volume=round(weekly_km, 1),
        )
