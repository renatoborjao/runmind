from datetime import date, datetime

from app.application.history.sleep_performance_analyzer import (
    SleepPerformanceAnalyzer,
    sleep_impact_plan_directive,
)
from app.domain.entities.activity import Activity
from app.domain.entities.daily_health import DailyHealth

REF = date(2026, 7, 28)


def _run(day: int, speed: float, hr: float = 150.0, km: float = 6.0) -> Activity:

    return Activity(
        id=day,
        name="run",
        sport="Run",
        start_date=datetime(2026, 7, day, 7, 0),
        timezone="America/Sao_Paulo",
        distance=km * 1000,
        moving_time=int(km * 1000 / speed),
        elapsed_time=int(km * 1000 / speed),
        average_speed=speed,
        max_speed=speed,
        average_heartrate=hr,
        max_heartrate=hr + 20,
        elevation_gain=0.0,
        elevation_high=None,
        elevation_low=None,
        start_latitude=None,
        start_longitude=None,
        end_latitude=None,
        end_longitude=None,
        kudos=0,
        comments=0,
        suffer_score=None,
        raw={},
    )


def _night(day: int, hours: float) -> DailyHealth:

    return DailyHealth(date=f"2026-07-{day:02d}", sleep_hours=hours)


def test_finds_pace_cost_of_short_sleep():
    """Corridas após noites curtas rendem menos no MESMO esforço (EF menor) ->
    o analisador acha o custo em s/km, com os números do atleta."""

    # bem-dormido: 8h, mais rápido (3.0 m/s a 150 bpm); mal-dormido: 5h, 2.85
    activities = (
        [_run(d, 3.0) for d in (20, 21, 22, 23)]
        + [_run(d, 2.85) for d in (24, 25, 26, 27)]
    )

    series = (
        [_night(d, 8.0) for d in (20, 21, 22, 23)]
        + [_night(d, 5.0) for d in (24, 25, 26, 27)]
    )

    impact = SleepPerformanceAnalyzer.analyze(activities, series, REF)

    assert impact.has_finding is True
    assert impact.pace_cost_sec is not None and impact.pace_cost_sec >= 5
    assert impact.low_sleep_runs == 4
    assert impact.rested_runs == 4


def test_no_finding_when_sleep_does_not_hurt():
    """Mesmo desempenho dormindo bem ou mal -> sem custo, sem achado."""

    activities = [_run(d, 3.0) for d in range(20, 28)]

    series = (
        [_night(d, 8.0) for d in (20, 21, 22, 23)]
        + [_night(d, 5.0) for d in (24, 25, 26, 27)]
    )

    assert SleepPerformanceAnalyzer.analyze(activities, series, REF).has_finding is False


def test_relative_split_for_chronic_short_sleeper():
    """Atleta que quase nunca passa de 7h (crônico): sem contraste absoluto,
    cai no corte RELATIVO (noites mais curtas vs mais longas DELE) e ainda
    acha o custo — é o cara que MAIS precisa dessa leitura."""

    # todas as noites < 7h: 5h (mais lento) vs 6h (mais rápido)
    activities = (
        [_run(d, 2.85) for d in (20, 21, 22, 23)]
        + [_run(d, 3.0) for d in (24, 25, 26, 27)]
    )

    series = (
        [_night(d, 5.0) for d in (20, 21, 22, 23)]
        + [_night(d, 6.0) for d in (24, 25, 26, 27)]
    )

    impact = SleepPerformanceAnalyzer.analyze(activities, series, REF)

    assert impact.has_finding is True
    assert impact.relative is True
    assert impact.pace_cost_sec >= 5


def test_no_finding_without_enough_runs_per_group():

    activities = [_run(20, 3.0), _run(24, 2.8)]  # 1 por grupo

    series = [_night(20, 8.0), _night(24, 5.0)]

    impact = SleepPerformanceAnalyzer.analyze(activities, series, REF)

    assert impact.has_finding is False


def test_plan_directive_empty_without_finding():

    from app.domain.entities.sleep_impact import SleepImpact

    assert sleep_impact_plan_directive(SleepImpact()) == ""

    directive = sleep_impact_plan_directive(
        SleepImpact(has_finding=True, pace_cost_sec=15)
    )

    assert "15s/km" in directive
