from datetime import datetime, timedelta

from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity

MONDAY = datetime(2026, 6, 29, 7, 0, 0)


def _run(weeks_ago: int, distance: float):

    return make_activity(
        start_date=MONDAY - timedelta(weeks=weeks_ago),
        distance=distance,
    )


def test_last_week_is_most_recent_not_biggest():

    history = TrainingHistory(
        activities=[
            _run(4, 30000.0),  # semana mais antiga é a maior
            _run(3, 8000.0),
            _run(2, 8000.0),
            _run(1, 8000.0),
            _run(0, 12000.0),  # semana mais recente
        ],
    )

    result = WeeklyVolumeAnalyzer.analyze(history)

    assert result["last_week"] == 12.0
    assert result["max_week"] == 30.0

    # média das 4 últimas semanas cronológicas, não das 4 maiores
    assert result["average_4_weeks"] == 9.0  # (8+8+8+12)/4


def test_empty_history_returns_zeros():

    result = WeeklyVolumeAnalyzer.analyze(
        TrainingHistory(activities=[]),
    )

    assert result == {
        "last_week": 0,
        "average_4_weeks": 0,
        "max_week": 0,
    }
