from statistics import median

from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_history import TrainingHistory

# Fragmento (aquecimento/desaquecimento solto, trecho curto) — não representa
# o ritmo de corrida; fora do cálculo de pace.
RUN_MIN_DISTANCE_KM = 1.5

# Acima disto é CAMINHADA, não corrida. Sem esse corte, uma caminhada de
# 11-12 min/km entrava na média e deixava os paces do plano lentos demais
# (bug da Fernanda: corre ~6:00 mas o plano prescrevia 7:30+).
WALK_PACE_CUTOFF = 9.0  # min/km


class RunnerMetricsBuilder:

    @staticmethod
    def build(
        history: TrainingHistory,
    ) -> RunnerMetrics:

        activities = history.activities

        run_paces = []

        all_paces = []

        for activity in activities:

            if activity.average_speed <= 0:
                continue

            pace = (
                (1000 / activity.average_speed)
                / 60
            )

            all_paces.append(pace)

            # só corridas de verdade contam pro pace de referência
            if (
                activity.distance / 1000 >= RUN_MIN_DISTANCE_KM
                and pace <= WALK_PACE_CUTOFF
            ):

                run_paces.append(pace)

        # sem corrida utilizável (só caminhou/fragmentos): usa tudo, pra não
        # quebrar o iniciante-caminhante
        sample = run_paces or all_paces

        if not sample:
            raise Exception(
                "Histórico insuficiente."
            )

        # MEDIANA (não média): robusta a um treino lento isolado ou a uma
        # caminhada que escapou do filtro
        average_pace = median(sample)

        weekly = WeeklyVolumeAnalyzer.analyze(
            history
        )

        return RunnerMetrics(

            easy_pace_min=round(
                average_pace - 0.25,
                2,
            ),

            easy_pace_max=round(
                average_pace + 0.35,
                2,
            ),

            threshold_pace=round(
                average_pace - 0.60,
                2,
            ),

            vo2_pace=round(
                average_pace - 1.10,
                2,
            ),

            average_hr=history.average_hr or 0,

            max_long_run=round(
                history.longest_run.distance / 1000,
                1,
            ),

            weekly_volume=weekly[
                "average_4_weeks"
            ],
        )