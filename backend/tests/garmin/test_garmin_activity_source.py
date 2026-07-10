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
