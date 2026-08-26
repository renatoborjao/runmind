from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history.sleep_performance_analyzer import (
    SLEEP_HURTS,
    SLEEP_INSUFFICIENT,
    SLEEP_SUSTAINS,
    SleepPerformanceAnalyzer,
    sleep_performance_directive,
)

REF = date(2026, 8, 26)


def _run(day: date, speed: float, hr: float = 150.0):
    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 7, 0),
        sport="Run",
        distance=6000.0,
        average_heartrate=hr,
        average_speed=speed,
        elevation_gain=None,
        air_temp_c=None,
    )


def _health(day: date, sleep: float):
    return SimpleNamespace(date=day.isoformat(), sleep_hours=sleep)


def _scenario(short_speed: float, rested_speed: float):
    """4 corridas após noite curta (5h) + 4 após noite normal (7h)."""

    acts, health = [], []

    for i in range(4):
        d = REF - timedelta(days=3 + i * 3)          # noites curtas
        acts.append(_run(d, short_speed))
        health.append(_health(d, 5.0))

        d2 = REF - timedelta(days=4 + i * 3)          # noites normais
        acts.append(_run(d2, rested_speed))
        health.append(_health(d2, 7.0))

    return acts, health


def _assess(acts, health):
    return SleepPerformanceAnalyzer.assess(
        acts, health, resting_hr=None, max_hr=None, reference_date=REF,
    )


def test_sustains_when_execution_holds_after_short_nights():
    """Rende IGUAL com pouco sono (mesma economia) -> SUSTAINS."""

    acts, health = _scenario(short_speed=3.0, rested_speed=3.0)

    reading = _assess(acts, health)

    assert reading.direction == SLEEP_SUSTAINS
    assert reading.runs_short >= 3 and reading.runs_rested >= 3
    assert reading.short_sleep_h == 5.0 and reading.rested_sleep_h == 7.0

    directive = sleep_performance_directive(reading)
    assert "entrega IGUAL" in directive
    assert "NÃO trave a dose" in directive


def test_hurts_when_execution_drops_after_short_nights():
    """Cai a economia após noites curtas (mais lento na mesma FC) -> HURTS."""

    acts, health = _scenario(short_speed=2.7, rested_speed=3.0)

    reading = _assess(acts, health)

    assert reading.direction == SLEEP_HURTS
    assert reading.pace_delta_sec and reading.pace_delta_sec > 0

    directive = sleep_performance_directive(reading)
    assert "CAI" in directive
    assert "segure a intensidade" in directive


def test_insufficient_without_enough_runs():

    acts, health = [], []
    for i in range(2):  # só 2 por grupo (< 3)
        d = REF - timedelta(days=3 + i)
        acts.append(_run(d, 3.0))
        health.append(_health(d, 5.0))
        d2 = REF - timedelta(days=10 + i)
        acts.append(_run(d2, 3.0))
        health.append(_health(d2, 7.0))

    assert _assess(acts, health).direction == SLEEP_INSUFFICIENT
    assert sleep_performance_directive(
        _assess(acts, health)
    ) == ""


def test_insufficient_without_sleep_contrast():
    """Ele dorme sempre ~6h: 'curto vs normal' não tem contraste real -> não
    julga (INSUFFICIENT)."""

    acts, health = [], []
    for i in range(4):
        d = REF - timedelta(days=3 + i * 3)
        acts.append(_run(d, 3.0))
        health.append(_health(d, 5.9))
        d2 = REF - timedelta(days=4 + i * 3)
        acts.append(_run(d2, 3.0))
        health.append(_health(d2, 6.1))

    assert _assess(acts, health).direction == SLEEP_INSUFFICIENT
