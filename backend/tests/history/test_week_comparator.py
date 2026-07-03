from datetime import date, datetime, timedelta

from app.application.history.week_comparator import WeekComparator
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity

# quarta-feira da semana ISO 27 de 2026 (segunda = 29/06)
REFERENCE = date(2026, 7, 1)

MONDAY = datetime(2026, 6, 29, 7, 0, 0)


def _run(weeks_ago: int, distance: float, moving_time: int, **overrides):

    return make_activity(
        start_date=MONDAY - timedelta(weeks=weeks_ago),
        distance=distance,
        moving_time=moving_time,
        **overrides,
    )


def test_compares_current_and_previous_calendar_weeks():

    history = TrainingHistory(
        activities=[
            # semana atual: 10 km em 50 min
            _run(0, 10000.0, 3000, average_heartrate=150.0),
            # semana anterior: 20 km em 110 min
            _run(1, 10000.0, 3000, average_heartrate=140.0),
            _run(1, 10000.0, 3600, average_heartrate=150.0),
        ],
    )

    result = WeekComparator.compare(
        history,
        reference_date=REFERENCE,
    )

    assert result["current_week"]["week_start"] == "2026-06-29"
    assert result["current_week"]["distance_km"] == 10.0
    assert result["current_week"]["runs"] == 1

    assert result["previous_week"]["week_start"] == "2026-06-22"
    assert result["previous_week"]["distance_km"] == 20.0
    assert result["previous_week"]["runs"] == 2

    delta = result["delta"]
    assert delta["distance_km"] == -10.0
    assert delta["runs"] == -1
    assert delta["volume_delta_percent"] == -50.0
    assert delta["avg_pace_min_km"] == -0.5  # 5.0 - 5.5
    assert delta["avg_hr"] == 5.0  # 150 - 145


def test_empty_previous_week_yields_zero_stats_and_none_percent():

    history = TrainingHistory(
        activities=[
            _run(0, 10000.0, 3000),
        ],
    )

    result = WeekComparator.compare(
        history,
        reference_date=REFERENCE,
    )

    assert result["previous_week"]["runs"] == 0
    assert result["previous_week"]["distance_km"] == 0

    delta = result["delta"]
    assert delta["volume_delta_percent"] is None
    assert delta["avg_pace_min_km"] is None
    assert delta["avg_hr"] is None
    assert delta["distance_km"] == 10.0
