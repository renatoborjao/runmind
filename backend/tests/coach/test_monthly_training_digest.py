from datetime import date, datetime

from app.application.history.monthly_training_digest import (
    MonthlyTrainingDigest,
)
from app.domain.entities.activity import Activity


def _run(y, m, d, km=6.0, speed=2.78, sport="Run") -> Activity:
    """speed em m/s; 2.78 ~ 6:00/km."""

    return Activity(
        id=int(f"{y}{m:02d}{d:02d}"), name="run", sport=sport,
        start_date=datetime(y, m, d, 7, 0),
        timezone="America/Sao_Paulo",
        distance=km * 1000, moving_time=int(km * 1000 / speed),
        elapsed_time=int(km * 1000 / speed),
        average_speed=speed, max_speed=speed,
        average_heartrate=150.0, max_heartrate=170.0,
        elevation_gain=0.0, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None, raw={},
    )


TODAY = date(2026, 8, 3)


def test_build_groups_by_month_recent_first():

    acts = [
        _run(2026, 5, 3, km=8),
        _run(2026, 5, 10, km=10),
        _run(2026, 6, 1, km=6),
    ]

    stats = MonthlyTrainingDigest.build(acts, TODAY)

    assert [(s.year, s.month) for s in stats] == [(2026, 6), (2026, 5)]

    maio = stats[1]

    assert maio.runs == 2
    assert maio.km == 18.0
    assert maio.longest_km == 10.0


def test_avg_pace_is_time_weighted():

    # dois treinos a 6:00/km -> pace médio do mês 6:00 (360s)
    acts = [_run(2026, 6, 1, km=5), _run(2026, 6, 8, km=10)]

    stats = MonthlyTrainingDigest.build(acts, TODAY)

    assert stats[0].avg_pace_sec == 360


def test_ignores_non_run_and_tiny():

    acts = [
        _run(2026, 6, 1, km=8),
        _run(2026, 6, 2, km=8, sport="Ride"),   # não é corrida
        _run(2026, 6, 3, km=0.4),               # fragmento < 1km
    ]

    stats = MonthlyTrainingDigest.build(acts, TODAY)

    assert len(stats) == 1
    assert stats[0].runs == 1


def test_render_uses_month_name_and_is_empty_without_runs():

    assert MonthlyTrainingDigest.render([], TODAY) == ""

    text = MonthlyTrainingDigest.render([_run(2026, 5, 3, km=8)], TODAY)

    assert "maio/2026" in text
    assert "8 km" in text
    assert "1 corrida," in text  # singular


def test_window_limits_months():

    acts = [_run(2026, m, 1, km=5) for m in range(1, 13)]  # 12 meses de 2026

    stats = MonthlyTrainingDigest.build(acts, TODAY, months=3)

    assert len(stats) == 3
    assert [(s.year, s.month) for s in stats] == [
        (2026, 12), (2026, 11), (2026, 10),
    ]
