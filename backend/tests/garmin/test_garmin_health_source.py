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


def _user_summary():
    """Formato real do get_user_summary (FR165). Consolida carga de vida, body
    battery e — de brinde — respiração de vigília + SpO2 ('Spo2' minúsculo)."""

    return {
        "totalSteps": 2966,
        "dailyStepGoal": 8890,
        "activeKilocalories": 38.0,
        "moderateIntensityMinutes": 0,
        "vigorousIntensityMinutes": 0,
        "intensityMinutesGoal": 150,
        "bodyBatteryMostRecentValue": 11,
        "bodyBatteryAtWakeTime": 37,
        "bodyBatteryHighestValue": 37,
        "bodyBatteryLowestValue": 5,
        "avgWakingRespirationValue": 14.0,
        "highestRespirationValue": 21.0,
        "lowestRespirationValue": 7.0,
        "averageSpo2": 95.0,
        "lowestSpo2": 86,
    }


def _respiration():
    """get_respiration_data (FR165): agrega a média de SONO ('Respiration'
    maiúsculo)."""

    return {
        "avgSleepRespirationValue": 13.0,
        "avgWakingRespirationValue": 14.0,
        "highestRespirationValue": 21.0,
        "lowestRespirationValue": 7.0,
    }


def _spo2():
    """get_spo2_data (FR165): média/mínima/sono ('SpO2' maiúsculo)."""

    return {
        "averageSpO2": 95.0,
        "avgSleepSpO2": 96.0,
        "lowestSpO2": 86,
    }


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
        "get_user_summary": _user_summary(),
        "get_respiration_data": _respiration(),
        "get_spo2_data": _spo2(),
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
        get_user_summary=None,
        get_respiration_data=None,
        get_spo2_data=None,
    )

    health = _fetch(garmin)

    assert health.sleep_hours is None
    assert health.hrv_last_night is None
    assert health.vo2max is None
    assert health.steps is None
    assert health.body_battery_most_recent is None
    assert health.respiration_sleep_avg is None
    assert health.spo2_avg is None
    assert health.date == "2026-07-21"


# --- tier-2: carga de vida, body battery, respiração, SpO2 ---


def test_maps_life_load_and_body_battery():

    health = _fetch(_fake_garmin())

    # carga de vida (esforço fora do treino) — dia parado
    assert health.steps == 2966
    assert health.steps_goal == 8890
    assert health.active_calories == 38
    assert health.intensity_minutes_moderate == 0
    assert health.intensity_minutes_vigorous == 0
    assert health.intensity_minutes_goal == 150

    # body battery: tanque baixo no dia
    assert health.body_battery_most_recent == 11
    assert health.body_battery_at_wake == 37
    assert health.body_battery_high == 37
    assert health.body_battery_low == 5


def test_maps_respiration_and_spo2_including_sleep_avgs():

    health = _fetch(_fake_garmin())

    # a média de SONO vem do endpoint dedicado (o summary não a tem)
    assert health.respiration_sleep_avg == 13.0
    assert health.respiration_waking_avg == 14.0
    assert health.respiration_high == 21.0
    assert health.respiration_low == 7.0

    assert health.spo2_avg == 95           # 95.0 -> int
    assert health.spo2_sleep_avg == 96
    assert health.spo2_low == 86


def test_sleep_avgs_survive_when_summary_present_but_dedicated_absent():

    # user_summary traz vigília/pico; sem os dedicados, a média de SONO fica
    # None mas o resto (do summary) sobrevive — set-if-present, sem apagar
    garmin = _fake_garmin(get_respiration_data=None, get_spo2_data=None)

    health = _fetch(garmin)

    assert health.respiration_waking_avg == 14.0   # do summary
    assert health.respiration_sleep_avg is None     # só vinha do dedicado
    assert health.spo2_avg == 95                     # do summary
    assert health.spo2_sleep_avg is None


def test_body_context_for_returns_only_filled_fields():

    garmin = _fake_garmin()

    ctx = GarminHealthSource.body_context_for(garmin, "2026-07-21")

    assert ctx["steps"] == 2966
    assert ctx["body_battery_most_recent"] == 11
    assert ctx["spo2_avg"] == 95
    # a varredura barata NÃO traz média de sono (não chama o endpoint dedicado)
    assert "respiration_sleep_avg" not in ctx
    assert "spo2_sleep_avg" not in ctx


def test_body_context_for_empty_when_no_summary():

    garmin = _fake_garmin(get_user_summary=None)

    assert GarminHealthSource.body_context_for(garmin, "2026-07-21") == {}
