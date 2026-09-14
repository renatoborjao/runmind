from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.home.calendar_builder import CalendarBuilder

MOD = "app.application.home.calendar_builder"
_TODAY = datetime(2026, 9, 14, 8, 0, 0)


def _act(day, km, secs, name, sport="Run", hr=150):
    return SimpleNamespace(
        start_date=datetime(2026, 9, day, 7, 0, 0),
        distance=km * 1000,
        moving_time=secs,
        average_heartrate=hr,
        elevation_gain=50,
        sport=sport,
        name=name,
    )


def _sess(day, wtype, km):
    return SimpleNamespace(
        day=day, workout_type=wtype, planned_distance_km=km,
        target_pace_min="6:20", target_pace_max="6:40",
    )


@contextmanager
def _patches(acts, plan, history=None, runner=None):
    with ExitStack() as st:
        st.enter_context(patch(f"{MOD}.now_local", return_value=_TODAY))
        st.enter_context(patch(f"{MOD}.ActivityArchiveRepository", lambda: SimpleNamespace(load_activities=lambda p: acts)))
        st.enter_context(patch(f"{MOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan, history=lambda p: history or [])))
        st.enter_context(patch(f"{MOD}.RunnerProfileRepository", lambda: SimpleNamespace(load=lambda p: runner or SimpleNamespace(target_race=None, race_date=None))))
        yield


def test_month_lists_executed_runs_with_ours_flag():
    acts = [
        _act(8, 8.2, 8 * 300, "São Paulo - Ritmind · Fartlek"),
        _act(9, 1.1, 400, "Corrida solta"),
        _act(2, 5.0, 1800, "Ritmind · Rodagem"),  # mês anterior? não, é set 2
    ]
    plan = SimpleNamespace(week_start=date(2026, 9, 14), sessions=[])

    with _patches(acts, plan):
        out = CalendarBuilder.month("t", 2026, 9)

    assert len(out["executed"]) == 3
    fartlek = [e for e in out["executed"] if e["date_iso"] == "2026-09-08"][0]
    assert fartlek["is_ours"] is True
    assert fartlek["kind"] == "tiro"
    solta = [e for e in out["executed"] if e["date_iso"] == "2026-09-09"][0]
    assert solta["is_ours"] is False


def test_month_excludes_other_months():
    acts = [_act(8, 8.0, 2400, "Ritmind · Rodagem")]
    plan = SimpleNamespace(week_start=date(2026, 9, 14), sessions=[])

    with _patches(acts, plan):
        out = CalendarBuilder.month("t", 2026, 10)  # outubro

    assert out["executed"] == []


def test_month_planned_future_only():
    acts = []
    plan = SimpleNamespace(
        week_start=date(2026, 9, 14),
        sessions=[_sess("Tuesday", "Fartlek", 8.0)],  # 15/09, futuro
    )

    with _patches(acts, plan):
        out = CalendarBuilder.month("t", 2026, 9)

    assert any(p["date_iso"] == "2026-09-15" for p in out["planned"])


def test_day_compares_planned_vs_executed_from_history():
    acts = [_act(6, 13.0, 13 * 375, "Ritmind · Longão")]
    current = SimpleNamespace(week_start=date(2026, 9, 14), sessions=[])
    history = [SimpleNamespace(week_start=date(2026, 9, 6), sessions=[_sess("Sunday", "Longão", 12.0)])]

    with _patches(acts, current, history=history):
        out = CalendarBuilder.day("t", "2026-09-06")

    assert out["executed"]["km"] == 13.0
    assert out["planned"]["workout_type"] == "Longão"
    assert out["planned"]["distance_km"] == 12.0
