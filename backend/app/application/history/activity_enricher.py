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

        elif (
            zone_from_hr := ActivityEnricher._zone_from_hr(activity, metrics)
        ) is not None:

            # régua de zonas DO ATLETA (relógio/reserva de FC) — a mesma do
            # gráfico. Antes o rótulo era relativo à FC média de costume e
            # contradizia o gráfico. Ver [[HrZoneResolver]].
            intensity, zone = zone_from_hr

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

        if activity.average_heartrate is not None and metrics.hr_zones is None:

            # sem régua de zonas (sem idade/FC máx), a intensidade acima é só
            # relativa à FC de costume — não é zona de FC, então não rotula
            zone = ""

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

            hr_zones=metrics.hr_zones,
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

    _INTENSITY_BY_ZONE = {
        1: "VERY_LOW",
        2: "LOW",
        3: "MEDIUM",
        4: "HIGH",
        5: "VERY_HIGH",
    }

    @staticmethod
    def _zone_from_hr(
        activity: Activity,
        metrics: RunnerMetrics,
    ) -> tuple[str, str] | None:
        """(intensidade, "Zn") da FC MÉDIA na régua do atleta; abaixo do piso
        de Z1 conta como Z1. None sem régua."""

        zones = metrics.hr_zones

        if zones is None or not activity.average_heartrate:

            return None

        number = zones.zone_of(activity.average_heartrate) or 1

        return ActivityEnricher._INTENSITY_BY_ZONE[number], f"Z{number}"

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