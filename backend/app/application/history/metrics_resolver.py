from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.history.runner_metrics import RunnerMetricsBuilder
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory

# Defaults conservadores de estreante (nunca correu / não informou volume).
ROOKIE_WEEKLY_KM = 6.0
ROOKIE_MAX_LONG_RUN = 3.0


class MetricsResolver:
    """Métricas do corredor com ou sem histórico:

    1. histórico com corridas -> RunnerMetricsBuilder (paces via PaceModel/VDOT
       real + volume real);
    2. sem histórico -> paces da FONTE (pace declarado no onboarding, modelo
       conservador) + volume declarado;
    3. sem nada -> defaults de estreante.

    Conforme os treinos do Strava chegam, o caminho 1 assume sozinho, e os
    paces sobem sozinhos com a forma. Ver [[PaceModelBuilder]]."""

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

            return RunnerMetricsBuilder.build(history, runner)

        # sem histórico utilizável: paces pela fonte (declarado/estreante),
        # volume pelo autodeclarado — enviesado pro conservador
        model = PaceModelBuilder.build(history, runner)

        weekly_km = runner.initial_weekly_km or ROOKIE_WEEKLY_KM

        return RunnerMetrics(
            easy_pace_min=model.easy_min,
            easy_pace_max=model.easy_max,
            threshold_pace=model.threshold,
            vo2_pace=model.interval,
            average_hr=0,
            max_long_run=max(
                round(weekly_km * 0.35, 1),
                ROOKIE_MAX_LONG_RUN,
            ),
            weekly_volume=round(weekly_km, 1),
        )
