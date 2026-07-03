from app.application.classification.training_classifier import (
    TrainingClassifier,
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

        pace = (
            (1000 / activity.average_speed)
            / 60
        )

        distance = activity.distance / 1000

        hr = activity.average_heartrate or metrics.average_hr

        indoor = activity.raw.get(
            "trainer",
            False,
        )

        # ---------------- Intensidade ----------------

        if hr >= metrics.average_hr + 10:

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

        efficiency = hr / pace

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
        )

        classification = TrainingClassifier.classify(

            enriched,

            metrics,

        )

        enriched.training_type = (
            classification.workout_type.value
        )

        return enriched