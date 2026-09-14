from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.home.workouts_builder import WorkoutsBuilder

HMOD = "app.application.home.home_summary_builder"
WMOD = "app.application.home.workouts_builder"

_TUE = datetime(2026, 9, 15, 8, 0, 0)


def _session(day, wtype):
    return SimpleNamespace(
        day=day, workout_type=wtype, objective="obj",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="5:00", target_pace_max="5:10", steps=[],
    )


def _build(plan, runner):
    with (
        patch(f"{WMOD}.now_local", return_value=_TUE),
        patch(f"{HMOD}.now_local", return_value=_TUE),
        patch(f"{WMOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan)),
        patch(f"{HMOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan)),
        patch(f"{WMOD}.RunnerProfileRepository", lambda: SimpleNamespace(load=lambda p: runner)),
    ):
        return WorkoutsBuilder.build("tester")


def test_week_has_dates_and_sessions():
    plan = SimpleNamespace(sessions=[_session("Tuesday", "Fartlek")])
    runner = SimpleNamespace(target_race=None, race_date=None, target_time=None)

    out = _build(plan, runner)

    assert len(out["week"]) == 7
    tue = [d for d in out["week"] if d["day_en"] == "Tuesday"][0]
    assert tue["is_today"] is True
    assert tue["date_iso"] == "2026-09-15"
    assert tue["session"]["workout_type"] == "Fartlek"
    # dia sem treino vem None
    assert [d for d in out["week"] if d["day_en"] == "Monday"][0]["session"] is None


def test_race_countdown():
    plan = SimpleNamespace(sessions=[])
    runner = SimpleNamespace(target_race="Prova 15k", race_date="2026-09-25", target_time="1:15:00")

    out = _build(plan, runner)

    assert out["race"]["name"] == "Prova 15k"
    assert out["race"]["days_until"] == 10  # 25 - 15


def test_no_race_when_profile_has_none():
    plan = SimpleNamespace(sessions=[])
    runner = SimpleNamespace(target_race=None, race_date=None, target_time=None)

    assert _build(plan, runner)["race"] is None
