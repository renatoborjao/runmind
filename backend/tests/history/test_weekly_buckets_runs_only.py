"""Números da semana só com corrida (Fernanda 14/09: 1 corrida de 8 km + 3
caminhadas saíram "16,3 km a 8:17" no resumo)."""

from datetime import datetime

from app.application.history.weekly_buckets import week_stats
from tests.coach.factories import make_activity


def _act(sport, km, pace_min_km, id_):

    speed = 1000 / (pace_min_km * 60)

    return make_activity(
        id=id_, sport=sport, distance=km * 1000, average_speed=speed,
        moving_time=int(km * 1000 / speed), start_date=datetime(2026, 9, 18, 7),
    )


def test_walks_stay_out_of_the_weeks_numbers():

    stats = week_stats([
        _act("Run", 8.01, 6.79, 1),
        _act("Walk", 2.15, 9.0, 2),
        _act("Walk", 2.15, 9.32, 3),
        _act("Walk", 4.01, 10.79, 4),
    ])

    assert (stats["runs"], stats["distance_km"], stats["avg_pace_min_km"]) == (
        1, 8.0, 6.79,
    )


def test_week_with_only_walks_is_an_empty_running_week():

    stats = week_stats([_act("Walk", 4.0, 10.0, 1)])

    assert (stats["runs"], stats["distance_km"], stats["avg_pace_min_km"]) == (
        0, 0.0, None,
    )
