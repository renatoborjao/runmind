from datetime import date, datetime, timedelta

from app.application.history.evolution_analyzer import EvolutionAnalyzer
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


def test_series_has_one_entry_per_week_including_empty_weeks():

    history = TrainingHistory(
        activities=[
            _run(0, 10000.0, 3000),
            _run(2, 8000.0, 2400),
        ],
    )

    result = EvolutionAnalyzer.analyze(
        history,
        weeks=4,
        reference_date=REFERENCE,
    )

    assert len(result["series"]) == 4

    # ordem cronológica: mais antiga primeiro
    assert result["series"][0]["week_start"] == "2026-06-08"
    assert result["series"][-1]["week_start"] == "2026-06-29"

    # semana vazia zera, não é pulada
    empty_week = result["series"][2]
    assert empty_week["runs"] == 0
    assert empty_week["distance_km"] == 0
    assert empty_week["avg_pace_min_km"] is None


def test_weekly_pace_is_distance_weighted():

    # 10 km em 50 min + 10 km em 60 min = 20 km em 110 min -> 5.5 min/km
    history = TrainingHistory(
        activities=[
            _run(0, 10000.0, 3000),
            _run(0, 10000.0, 3600),
        ],
    )

    result = EvolutionAnalyzer.analyze(
        history,
        weeks=1,
        reference_date=REFERENCE,
    )

    week = result["series"][0]
    assert week["distance_km"] == 20.0
    assert week["avg_pace_min_km"] == 5.5


def test_volume_trend_up_when_recent_weeks_bigger():

    activities = [
        _run(weeks_ago, 20000.0, 6000) for weeks_ago in range(4)
    ] + [
        _run(weeks_ago, 10000.0, 3000) for weeks_ago in range(4, 8)
    ]

    result = EvolutionAnalyzer.analyze(
        TrainingHistory(activities=activities),
        weeks=8,
        reference_date=REFERENCE,
    )

    volume_trend = result["trends"]["volume"]
    assert volume_trend["direction"] == "up"
    assert volume_trend["delta_percent"] == 100.0


def test_trend_stable_when_volumes_equal():

    activities = [
        _run(weeks_ago, 10000.0, 3000) for weeks_ago in range(8)
    ]

    result = EvolutionAnalyzer.analyze(
        TrainingHistory(activities=activities),
        weeks=8,
        reference_date=REFERENCE,
    )

    assert result["trends"]["volume"]["direction"] == "stable"
    assert result["trends"]["volume"]["delta_percent"] == 0.0


def test_trend_is_stable_with_none_delta_when_no_previous_data():

    history = TrainingHistory(
        activities=[_run(0, 10000.0, 3000)],
    )

    result = EvolutionAnalyzer.analyze(
        history,
        weeks=8,
        reference_date=REFERENCE,
    )

    assert result["trends"]["volume"] == {
        "delta_percent": None,
        "direction": "stable",
    }
