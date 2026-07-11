"""Testa o mapeamento Garmin -> IntervalAnalysis exata e os streams. Os
nomes de campo aqui seguem o formato conhecido do Garmin Connect; a
verificação final é contra uma atividade real (garmin_dump.py)."""

from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)


def test_exact_interval_from_typed_splits():
    """6x800: as voltas ROTULADAS viram reps exatos, sem inferência."""

    typed = {
        "splits": [
            {"type": "WARMUP", "distance": 2000, "averageSpeed": 2.6,
             "averageHR": 130},
            # 3 tiros + recuperações (esforço=INTERVAL, pausa=RECOVERY)
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 165, "maxHR": 170},
            {"type": "RECOVERY", "distance": 400, "averageSpeed": 2.4,
             "averageHR": 140},
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 168, "maxHR": 172},
            {"type": "RECOVERY", "distance": 400, "averageSpeed": 2.4,
             "averageHR": 138},
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 169, "maxHR": 174},
            {"type": "COOLDOWN", "distance": 1500, "averageSpeed": 2.6,
             "averageHR": 128},
        ]
    }

    interval = GarminActivitySource._exact_interval(typed)

    assert interval is not None
    assert interval.rep_count == 3  # exato: 3 tiros, nem 2 nem 4
    assert len(interval.reps) == 3
    assert interval.reps[0]["distance_m"] == 800
    # FC de recuperação vem das voltas RECOVERY
    assert interval.avg_recovery_hr == 139  # (140+138)/2 ~ 139
    assert interval.avg_peak_hr == 172  # (170+172+174)/3 = 172


def test_no_interval_when_less_than_two_efforts():

    typed = {"splits": [
        {"type": "RUN", "distance": 8000, "averageSpeed": 2.8},
    ]}

    assert GarminActivitySource._exact_interval(typed) is None


def test_exact_interval_handles_real_suffixed_types():
    """Voltas reais do Garmin vêm com sufixo: INTERVAL_ACTIVE (esforço) e
    INTERVAL_RECOVERY (pausa). O matching por substring cobre — e não
    confunde RECOVERY com esforço."""

    typed = {"splits": [
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.5,
         "averageHR": 165, "maxHR": 170},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.4,
         "averageHR": 140},
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.5,
         "averageHR": 168, "maxHR": 172},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.4,
         "averageHR": 138},
    ]}

    interval = GarminActivitySource._exact_interval(typed)

    assert interval.rep_count == 2
    assert interval.avg_recovery_hr == 139
    assert interval.avg_peak_hr == 171


def test_longao_typed_splits_do_not_become_interval():
    """Longão real (typed_splits do renato2 hoje): 1 bloco INTERVAL_ACTIVE +
    voltas RWD_* de run-walk-detection -> NÃO é intervalado."""

    typed = {"splits": [
        {"type": "RWD_RUN", "distance": 8261, "averageSpeed": 2.61,
         "averageHR": 160},
        {"type": "INTERVAL_ACTIVE", "distance": 12212, "averageSpeed": 2.62,
         "averageHR": 160, "maxHR": 169},
        {"type": "RWD_STAND", "distance": None, "averageSpeed": 0},
        {"type": "RWD_WALK", "distance": 17, "averageSpeed": 2.67,
         "averageHR": 143},
        {"type": "RWD_RUN", "distance": 3933, "averageSpeed": 2.63,
         "averageHR": 162},
    ]}

    assert GarminActivitySource._exact_interval(typed) is None


def test_to_activity_reads_nested_dtos():
    """get_activity devolve DTOs aninhados (summaryDTO/activityTypeDTO/
    timeZoneUnitDTO) — regressão do bug que lia campos planos e zerava tudo."""

    summary = {
        "activityId": 123,
        "activityName": "Longão 12km",
        "activityTypeDTO": {"typeKey": "running"},
        "timeZoneUnitDTO": {"timeZone": "America/Sao_Paulo"},
        "summaryDTO": {
            "distance": 12212.34, "movingDuration": 4656,
            "elapsedDuration": 4709, "duration": 4661,
            "averageSpeed": 2.62, "maxSpeed": 3.16,
            "averageHR": 160, "maxHR": 169, "elevationGain": 39,
            "maxElevation": 762, "minElevation": 749,
            "startLatitude": -23.5, "startLongitude": -46.6,
            "startTimeGMT": "2026-07-11T10:00:27.0",
        },
    }

    act = GarminActivitySource._to_activity(123, summary, dict(summary))

    assert act.name == "Longão 12km"
    assert act.sport == "Run"
    assert act.timezone == "America/Sao_Paulo"
    assert act.distance == 12212.34
    assert act.moving_time == 4656
    assert act.average_heartrate == 160.0
    assert act.max_heartrate == 169.0
    assert act.elevation_gain == 39.0
    assert act.start_latitude == -23.5


def test_rich_metrics_keeps_only_present_fields():

    summary_dto = {
        "averageRunCadence": 162, "trainingEffect": 5.0,
        "trainingEffectLabel": "LACTATE_THRESHOLD", "directWorkoutRpe": 50,
        "averagePower": 328, "somethingUnmapped": 1,
        # ausentes: averageTemperature, maxPower...
    }

    metrics = GarminActivitySource._rich_metrics(summary_dto)

    assert metrics["avg_cadence"] == 162
    assert metrics["training_effect_label"] == "LACTATE_THRESHOLD"
    assert metrics["workout_rpe"] == 50
    assert metrics["avg_power"] == 328
    # campo não mapeado não entra; campo ausente não vira None
    assert "somethingUnmapped" not in metrics
    assert "avg_temperature" not in metrics


def test_streams_from_details_parallel_arrays():

    details = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directSpeed"},
            {"metricsIndex": 1, "key": "directHeartRate"},
            {"metricsIndex": 2, "key": "sumDistance"},
        ],
        "activityDetailMetrics": [
            {"metrics": [3.5, 165, 100]},
            {"metrics": [3.4, 166, 110]},
        ],
    }

    streams = GarminActivitySource._streams(details)

    assert streams["velocity_smooth"] == [3.5, 3.4]
    assert streams["heartrate"] == [165, 166]
    assert streams["distance"] == [100, 110]


def test_sport_mapping():

    assert GarminActivitySource._sport("running") == "Run"
    assert GarminActivitySource._sport("treadmill_running") == "Run"
    assert GarminActivitySource._sport("trail_running") == "TrailRun"
    assert GarminActivitySource._sport("walking") == "Walk"


def test_structure_builder_prefers_exact_garmin_interval():
    """Quando o raw traz _garmin_interval (voltas rotuladas), o builder usa
    ele em vez do detector fuzzy por stream."""

    from datetime import datetime

    from app.application.history.workout_structure_builder import (
        WorkoutStructureBuilder,
    )
    from app.domain.entities.activity import Activity
    from app.domain.entities.interval_analysis import IntervalAnalysis

    exact = IntervalAnalysis(
        rep_count=6,
        avg_rep_pace=4.75,
        avg_peak_hr=170,
        avg_recovery_hr=138,
        reps=[{"distance_m": 800, "pace": 4.75, "peak_hr": 170}] * 6,
    )

    activity = Activity(
        id=1, name="Tiros", sport="Run",
        start_date=datetime(2026, 7, 14, 7, 0, 0), timezone="UTC",
        distance=9000, moving_time=2700, elapsed_time=2700,
        average_speed=3.3, max_speed=3.6,
        average_heartrate=150, max_heartrate=174,
        elevation_gain=10, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None,
        raw={"_garmin_interval": exact, "_streams": {}},
    )

    structure = WorkoutStructureBuilder.build(activity)

    assert structure.interval is exact
    assert structure.interval.rep_count == 6
    assert structure.is_interval is True
