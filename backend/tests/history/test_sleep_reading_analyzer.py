from app.application.history.sleep_reading_analyzer import (
    SleepReadingAnalyzer,
)
from app.domain.entities.body_reading import FALLING, RISING
from app.domain.entities.daily_health import DailyHealth


def _night(day: str, hours: float | None, score: int | None = None) -> DailyHealth:

    return DailyHealth(date=day, sleep_hours=hours, sleep_score=score)


def _series(hours: list[float]):

    return [
        _night(f"2026-07-{10 + i:02d}", h) for i, h in enumerate(hours)
    ]


def test_no_nights_has_no_data():

    reading = SleepReadingAnalyzer.analyze([])

    assert reading.has_data is False
    assert reading.avg_hours is None


def test_average_and_short_nights():

    reading = SleepReadingAnalyzer.analyze(_series([6.0, 5.0, 8.0, 7.5]))

    assert reading.nights_counted == 4
    assert reading.avg_hours == 6.6
    # abaixo do piso de 7h: 6.0 e 5.0
    assert reading.short_nights == 2
    assert reading.last_night_hours == 7.5


def test_debt_when_average_below_floor():

    assert SleepReadingAnalyzer.analyze(_series([5.5, 6.0, 5.8, 6.2])).debt is True
    assert SleepReadingAnalyzer.analyze(_series([7.5, 8.0, 7.2, 7.8])).debt is False


def test_direction_rises_when_sleeping_more():
    """Metade recente dormindo bem mais que a anterior -> RISING."""

    reading = SleepReadingAnalyzer.analyze(_series([5.0, 5.2, 7.5, 7.8]))

    assert reading.direction == RISING


def test_direction_falls_when_sleeping_less():

    reading = SleepReadingAnalyzer.analyze(_series([8.0, 7.8, 5.5, 5.2]))

    assert reading.direction == FALLING


def test_consistency_irregular_with_high_spread():

    irregular = SleepReadingAnalyzer.analyze(_series([8.5, 4.5, 7.5, 5.0]))

    assert irregular.consistency == "irregular"

    regular = SleepReadingAnalyzer.analyze(_series([7.0, 7.2, 6.9, 7.1]))

    assert regular.consistency == "regular"


def test_garmin_score_is_the_most_recent():

    series = [
        _night("2026-07-10", 7.0, score=60),
        _night("2026-07-11", 7.2, score=80),
    ]

    assert SleepReadingAnalyzer.analyze(series).sleep_score == 80
