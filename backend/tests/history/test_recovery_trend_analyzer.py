from app.application.history.recovery_trend_analyzer import (
    RecoveryTrendAnalyzer,
)
from app.domain.entities.body_reading import FALLING, RISING, STABLE
from app.domain.entities.daily_health import DailyHealth


def _series(hrv=None, rhr=None, sleep=None):

    n = max(len(x) for x in (hrv, rhr, sleep) if x) if any((hrv, rhr, sleep)) else 0

    out = []

    for i in range(n):

        out.append(
            DailyHealth(
                date=f"2026-07-{i + 1:02d}",
                hrv_weekly_avg=hrv[i] if hrv else None,
                resting_hr=rhr[i] if rhr else None,
                sleep_hours=sleep[i] if sleep else None,
            )
        )

    return out


def test_rising_hrv_is_detected():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[40, 41, 42, 43, 48, 49, 50, 51])
    )

    assert trend.hrv_direction == RISING
    assert trend.hrv_recent == 51


def test_falling_resting_hr_reads_as_recovery_improving():

    # FC de repouso caindo (66->60) = recuperação MELHORANDO -> RISING (POV rec)
    trend = RecoveryTrendAnalyzer.analyze(
        _series(rhr=[66, 66, 65, 65, 60, 60, 60, 60])
    )

    assert trend.rhr_direction == RISING


def test_falling_hrv_is_flagged():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[52, 51, 50, 49, 44, 43, 42, 40])
    )

    assert trend.hrv_direction == FALLING


def test_too_few_points_stays_stable():

    trend = RecoveryTrendAnalyzer.analyze(_series(hrv=[40, 55]))

    assert trend.hrv_direction == STABLE


def test_sleep_avg_and_short_nights():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(sleep=[4.0, 4.5, 5.0, 7.5, 8.0, 6.2])
    )

    # 3 noites < 6h (4.0, 4.5, 5.0)
    assert trend.short_nights == 3
    assert trend.nights_counted == 6
    assert trend.sleep_avg_hours == round(sum([4.0, 4.5, 5.0, 7.5, 8.0, 6.2]) / 6, 1)


def test_empty_series_has_no_data():

    trend = RecoveryTrendAnalyzer.analyze([])

    assert trend.has_data is False
    assert trend.days_covered == 0
