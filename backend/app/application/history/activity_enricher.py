from app.application.classification.training_classifier import (
    TrainingClassifier,
)
from app.application.history.workout_structure_builder import (
    WorkoutStructureBuilder,
)
from app.domain.entities.activity import Activity
from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.runner_metrics import RunnerMetrics


class ActivityEnricher:

    @staticmethod
    def enrich(
        activity: Activity,
        metrics: RunnerMetrics,
    ) -> EnrichedActivity:

        # Sem velocidade média (corrida sem distância — esteira/HIIT sem
        # sensor de distância) não dá pra derivar pace. Guard defensivo pra
        # NUNCA dividir por zero; a entrada (webhook/poller) já pula a análise
        # dessas atividades, então na prática isto é cinto-e-suspensório.
        pace = (
            (1000 / activity.average_speed) / 60
            if activity.average_speed
            else 0.0
        )

        distance = activity.distance / 1000

        hr = activity.average_heartrate or metrics.average_hr

        indoor = activity.raw.get(
            "trainer",
            False,
        )

        # ---------------- Intensidade ----------------

        if activity.average_heartrate is None:

            # Sem FC real não dá pra fingir "MEDIUM" com a FC média
            # emprestada — deriva a intensidade do pace do corredor.
            intensity, zone = ActivityEnricher._intensity_from_pace(
                pace,
                metrics,
            )

        elif hr >= metrics.average_hr + 10:

            intensity = "VERY_HIGH"

            zone = "Z5"

        elif hr >= metrics.average_hr + 5:

            intensity = "HIGH"

            zone = "Z4"

        elif hr >= metrics.average_hr - 5:

            intensity = "MEDIUM"

            zone = "Z3"

        elif hr >= metrics.average_hr - 12:

            intensity = "LOW"

            zone = "Z2"

        else:

            intensity = "VERY_LOW"

            zone = "Z1"

        # ---------------- Carga ----------------

        suffer = activity.suffer_score or 0

        elevation = activity.elevation_gain

        elevation_factor = 1 + (
            elevation / 1000
        )

        training_load = (

            distance
            * hr
            * elevation_factor

        )

        if suffer:

            training_load += suffer

        fatigue = training_load / 25

        if fatigue < 35:

            recovery = 24

        elif fatigue < 60:

            recovery = 36

        else:

            recovery = 48

        efficiency = hr / pace if pace else 0.0

        structure = WorkoutStructureBuilder.build(activity)

        enriched = EnrichedActivity(

            activity=activity,

            pace_min_km=round(
                pace,
                2,
            ),

            training_type="UNKNOWN",

            intensity=intensity,

            estimated_zone=zone,

            training_load=round(
                training_load,
                1,
            ),

            fatigue_score=round(
                fatigue,
                1,
            ),

            recovery_hours=recovery,

            efficiency_score=round(
                efficiency,
                1,
            ),

            indoor=indoor,

            structure=structure,
        )

        classification = TrainingClassifier.classify(

            enriched,

            metrics,

            structure,

        )

        enriched.training_type = (
            classification.workout_type.value
        )

        return enriched

    @staticmethod
    def _intensity_from_pace(
        pace: float,
        metrics: RunnerMetrics,
    ) -> tuple[str, str]:

        if pace <= metrics.vo2_pace:

            return "VERY_HIGH", "Z5"

        if pace <= metrics.threshold_pace:

            return "HIGH", "Z4"

        if pace <= metrics.easy_pace_min:

            return "MEDIUM", "Z3"

        if pace <= metrics.easy_pace_max:

            return "LOW", "Z2"

        return "VERY_LOW", "Z1"