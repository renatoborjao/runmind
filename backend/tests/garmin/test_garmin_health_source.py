from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)

MODULE = "app.infrastructure.integrations.garmin.garmin_health_source"


# --- fixtures no FORMATO REAL do Garmin (dump da conta do Renato, FR165) ---

def _sleep(seconds=16380, score=63):

    return {
        "dailySleepDTO": {
            "sleepTimeSeconds": seconds,
            "deepSleepSeconds": 3540,
            "remSleepSeconds": 4920,
            "lightSleepSeconds": 7920,
            "awakeSleepSeconds": 0,
            "sleepScores": {"overall": {"value": score, "qualifierKey": "FAIR"}},
        },
        "bodyBatteryChange": 58,
        "restingHeartRate": 60,
    }


def _hrv(status="NONE"):

    return {
        "hrvSummary": {
            "lastNightAvg": 63,
            "weeklyAvg": 52,
            "baseline": None,
            "status": status,
        }
    }


def _stress():

    return {"avgStressLevel": 29, "maxStressLevel": 90}


def _max_metrics():

    return [{"generic": {"vo2MaxPreciseValue": 44.4, "vo2MaxValue": 44.0}}]


def _fake_garmin(**overrides):
    """Objeto Garmin falso: métodos devolvem as fixtures (ou o override)."""

    defaults = {
        "get_sleep_data": _sleep(),
        "get_hrv_data": _hrv(),
        "get_all_day_stress": _stress(),
        "get_max_metrics": _max_metrics(),
        "get_training_readiness": [],  # vazio no FR165
        "get_training_status": {
            "mostRecentTrainingStatus": None,
            "mostRecentTrainingLoadBalance": None,
        },
    }

    defaults.update(overrides)

    methods = {name: (lambda v=val: lambda *a, **k: v)() for name, val in defaults.items()}

    return SimpleNamespace(**methods)


def _fetch(garmin):

    with patch(f"{MODULE}.GarminClient.connect", return_value=garmin):

        return GarminHealthSource.fetch("renato2", "2026-07-21")


def test_maps_basic_watch_primitives():

    health = _fetch(_fake_garmin())

    assert health.date == "2026-07-21"
    assert health.sleep_hours == 4.55
    assert health.deep_sleep_hours == 0.98
    assert health.sleep_score == 63
    assert health.hrv_last_night == 63
    assert health.hrv_weekly_avg == 52
    assert health.hrv_status == "NONE"
    assert health.stress_avg == 29
    assert health.stress_max == 90
    assert health.body_battery_change == 58
    assert health.resting_hr == 60
    assert health.vo2max == 44.4


def test_premium_computed_fields_absent_on_basic_watch():

    # FR165: readiness/training_status vazios -> None, sem quebrar
    health = _fetch(_fake_garmin())

    assert health.readiness_score is None
    assert health.readiness_level is None
    assert health.training_status is None
    assert health.training_load_balance is None


# --- FORMATO REAL do FR265 (dump da conta do João, 2026-09-05) ---

_DEVICE = "3628537299"


def _training_status_fr265(
    status_phrase="PRODUCTIVE_3",
    balance_phrase="AEROBIC_HIGH_SHORTAGE",
    balance_map_null=False,
):
    """mostRecentTrainingStatus/LoadBalance ANINHADOS por deviceId, como o
    FR265 realmente devolve."""

    balance_map = None if balance_map_null else {
        _DEVICE: {
            "trainingBalanceFeedbackPhrase": balance_phrase,
            "primaryTrainingDevice": True,
        }
    }

    return {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                _DEVICE: {
                    "trainingStatus": 7,
                    "trainingStatusFeedbackPhrase": status_phrase,
                    "acuteTrainingLoadDTO": {"acwrStatus": "OPTIMAL"},
                    "primaryTrainingDevice": True,
                }
            }
        },
        "mostRecentTrainingLoadBalance": {
            "metricsTrainingLoadBalanceDTOMap": balance_map
        },
    }


def test_premium_readiness_and_status_used_when_present():

    # FR265: readiness (lista) + training status/balance ANINHADOS por device
    garmin = _fake_garmin(
        get_training_readiness=[{"score": 82, "level": "HIGH", "sleepScore": 90}],
        get_training_status=_training_status_fr265(),
    )

    health = _fetch(garmin)

    assert health.readiness_score == 82
    assert health.readiness_level == "HIGH"
    # "PRODUCTIVE_3" -> rótulo canônico "PRODUCTIVE" (o formatter traduz)
    assert health.training_status == "PRODUCTIVE"
    assert health.training_load_balance == "AEROBIC_HIGH_SHORTAGE"


def test_no_status_phrase_maps_to_none():

    # relógio ainda sem base suficiente: "NO_STATUS_2" + mapa de balance nulo
    garmin = _fake_garmin(
        get_training_status=_training_status_fr265(
            status_phrase="NO_STATUS_2", balance_map_null=True
        ),
    )

    health = _fetch(garmin)

    assert health.training_status is None
    assert health.training_load_balance is None


def test_missing_endpoint_never_crashes():

    # um endpoint que explode / device sem a métrica -> aquele campo None,
    # o resto do snapshot continua
    def boom(*a, **k):

        raise RuntimeError("device sem sono")

    garmin = _fake_garmin()

    garmin.get_sleep_data = boom

    health = _fetch(garmin)

    assert health.sleep_hours is None  # seção que falhou
    assert health.vo2max == 44.4       # o resto sobrevive


def test_no_data_returns_all_none():

    garmin = _fake_garmin(
        get_sleep_data=None,
        get_hrv_data=None,
        get_all_day_stress=None,
        get_max_metrics=None,
        get_training_readiness=None,
        get_training_status=None,
    )

    health = _fetch(garmin)

    assert health.sleep_hours is None
    assert health.hrv_last_night is None
    assert health.vo2max is None
    assert health.date == "2026-07-21"
