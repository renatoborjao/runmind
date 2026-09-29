from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.home import week_load_builder
from app.application.home.week_load_builder import WeekLoadBuilder

TODAY = date(2026, 9, 29)  # terça; a semana em andamento começa em 28/09
THIS_MONDAY = date(2026, 9, 28)


def _run(day: date, km: float):

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 7, 0),
        distance=km * 1000,
    )


def _week(monday: date, kms: list[float]):
    """Corridas nos dias seguintes à segunda dada (1 por valor)."""

    return [_run(monday + timedelta(days=i * 2), km) for i, km in enumerate(kms)]


def _build(monkeypatch, runs, plan=None):

    monkeypatch.setattr(week_load_builder, "merged_runs", lambda profile: runs)

    monkeypatch.setattr(
        week_load_builder,
        "WeeklyPlanRepository",
        lambda: SimpleNamespace(load=lambda profile: plan),
    )

    return WeekLoadBuilder.build("x", today=TODAY)


def _four_normal_weeks():

    # 31/08, 07/09, 14/09, 21/09: 3 corridas por semana, 30 km
    return sum(
        (_week(THIS_MONDAY - timedelta(weeks=w), [8, 8, 14]) for w in range(1, 5)),
        [],
    )


def test_current_week_against_the_average_of_the_last_four(monkeypatch):

    runs = _four_normal_weeks() + [_run(date(2026, 9, 29), 9.0)]

    out = _build(monkeypatch, runs)

    assert out["km"] == 9.0
    assert out["runs"] == 1
    assert out["avg_km"] == 30.0
    assert out["avg_runs"] == 3.0


def test_a_stopped_week_does_not_drag_the_average(monkeypatch):

    # semana de 14/09 parada (viagem): a média é das semanas que ele treinou
    runs = [
        r
        for r in _four_normal_weeks()
        if not (date(2026, 9, 14) <= r.start_date.date() <= date(2026, 9, 20))
    ]

    out = _build(monkeypatch, runs)

    assert out["avg_km"] == 30.0


def test_no_average_without_two_active_weeks(monkeypatch):

    runs = _week(THIS_MONDAY - timedelta(weeks=1), [8, 8, 14])

    out = _build(monkeypatch, runs)

    assert out["avg_km"] is None
    assert out["avg_runs"] is None


def test_planned_runs_only_when_the_plan_is_this_calendar_week(monkeypatch):

    runs = _four_normal_weeks()

    this_week = SimpleNamespace(week_start=THIS_MONDAY, sessions=[1, 2, 3])
    next_week = SimpleNamespace(
        week_start=THIS_MONDAY + timedelta(weeks=1), sessions=[1, 2, 3]
    )
    from_json = SimpleNamespace(week_start="2026-09-28", sessions=[1, 2, 3, 4])

    assert _build(monkeypatch, runs, this_week)["planned_runs"] == 3
    assert _build(monkeypatch, runs, next_week)["planned_runs"] is None
    assert _build(monkeypatch, runs, from_json)["planned_runs"] == 4
    assert _build(monkeypatch, runs, None)["planned_runs"] is None


def test_no_runs_hides_the_card(monkeypatch):

    assert _build(monkeypatch, []) is None
