from app.application.classification.training_classification import (
    TrainingClassification,
)
from app.application.classification.training_score import (
    TrainingScore,
)
from app.application.classification.workout_type import (
    WorkoutType,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.runner_metrics import (
    RunnerMetrics,
)


# Piso absoluto para pontuar como longão: sem isso, um histórico
# minúsculo (max_long_run de 100 m) faz qualquer trote virar LONG_RUN.
MIN_LONG_RUN_KM = 5.0


class TrainingClassifier:

    @staticmethod
    def classify(
        activity: EnrichedActivity,
        metrics: RunnerMetrics,
    ) -> TrainingClassification:

        distance = activity.activity.distance / 1000

        pace = activity.pace_min_km

        hr = activity.activity.average_heartrate or metrics.average_hr

        duration = activity.activity.moving_time / 60

        scores = [

            TrainingScore(WorkoutType.RECOVERY),

            TrainingScore(WorkoutType.EASY),

            TrainingScore(WorkoutType.TEMPO),

            TrainingScore(WorkoutType.VO2),

            TrainingScore(WorkoutType.LONG_RUN),

        ]

        # ---------------- DISTÂNCIA ----------------

        if (
            distance >= metrics.max_long_run * 0.90
            and distance >= MIN_LONG_RUN_KM
        ):

            scores[4].add(
                60,
                "Distância típica de longão",
            )

        elif distance >= metrics.max_long_run * 0.60:

            scores[2].add(
                15,
                "Distância moderada",
            )

        else:

            scores[1].add(
                10,
                "Distância curta",
            )

        # ---------------- PACE ----------------

        if pace <= metrics.vo2_pace:

            scores[3].add(
                45,
                "Pace de VO2",
            )

        elif pace <= metrics.threshold_pace:

            scores[2].add(
                35,
                "Pace de limiar",
            )

        elif pace <= metrics.easy_pace_max:

            scores[1].add(
                25,
                "Pace confortável",
            )

        else:

            scores[0].add(
                20,
                "Pace regenerativo",
            )

        # ---------------- FC ----------------

        if hr >= metrics.average_hr + 15:

            scores[3].add(
                40,
                "FC muito alta",
            )

        elif hr >= metrics.average_hr + 8:

            scores[2].add(
                30,
                "FC alta",
            )

        elif hr >= metrics.average_hr - 5:

            scores[1].add(
                20,
                "FC moderada",
            )

        else:

            scores[0].add(
                20,
                "FC baixa",
            )

        # ---------------- DURAÇÃO ----------------

        if duration >= 90 and distance >= MIN_LONG_RUN_KM:

            scores[4].add(
                30,
                "Treino longo",
            )

        elif duration >= 40:

            scores[2].add(
                20,
                "Tempo sustentado",
            )

        elif duration <= 25:

            scores[3].add(
                15,
                "Sessão curta",
            )

        winner = max(
            scores,
            key=lambda s: s.score,
        )

        confidence = min(
            winner.score / 100,
            0.99,
        )

        return TrainingClassification(

            workout_type=winner.workout,

            intensity=activity.intensity,

            estimated_zone=activity.estimated_zone,

            confidence=confidence,

            reasons=winner.reasons,

        )