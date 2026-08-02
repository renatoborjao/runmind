from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory

# Fragmento (aquecimento/desaquecimento solto, trecho curto) — não representa
# o ritmo de corrida. Mantido aqui porque race_time_predictor e
# personal_record_detector importam estas constantes.
RUN_MIN_DISTANCE_KM = 1.5

# Acima disto é CAMINHADA, não corrida.
WALK_PACE_CUTOFF = 9.0  # min/km


class RunnerMetricsBuilder:
    """Métricas do corredor a partir do histórico REAL. Os PACES agora saem da
    fonte única (PaceModel/VDOT do melhor esforço real + trava de condição) —
    não mais de offsets chutados sobre a mediana. Volume/FC/maior treino
    seguem do histórico. Ver [[PaceModelBuilder]]."""

    @staticmethod
    def build(
        history: TrainingHistory,
        runner: RunnerProfile | None = None,
    ) -> RunnerMetrics:

        model = PaceModelBuilder.build(history, runner)

        weekly = WeeklyVolumeAnalyzer.analyze(history)

        return RunnerMetrics(
            easy_pace_min=model.easy_min,
            easy_pace_max=model.easy_max,
            threshold_pace=model.threshold,
            vo2_pace=model.interval,
            average_hr=history.average_hr or 0,
            max_long_run=round(history.longest_run.distance / 1000, 1),
            weekly_volume=weekly["average_4_weeks"],
        )
