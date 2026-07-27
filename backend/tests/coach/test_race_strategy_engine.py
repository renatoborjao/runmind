from datetime import date

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal


def _goal(distance_km=10.0, target_time="00:50:00", race_date=None):
    return TrainingGoal(
        name="10k sub-50",
        distance_km=distance_km,
        target_time=target_time,
        race_date=race_date or date(2026, 8, 23),
    )


def _metrics(threshold=5.5):
    return RunnerMetrics(
        easy_pace_min=6.0, easy_pace_max=6.5, threshold_pace=threshold,
        vo2_pace=4.5, average_hr=150.0, max_long_run=16.0, weekly_volume=30.0,
    )


def test_plan_from_target_time():

    plan = RaceStrategyEngine.plan(_goal(10.0, "00:50:00"))

    assert plan is not None
    assert plan.estimated is False
    assert plan.total_minutes == 50.0
    assert plan.avg_pace_min == 5.0
    # abre ~5s mais devagar, fecha ~5s mais forte
    assert plan.open_pace_min > plan.avg_pace_min > plan.close_pace_min
    # passagem na metade correndo a 1a metade controlada (~25 min +)
    assert 25.0 < plan.halfway_minutes < 26.5


def test_message_has_pace_and_splits():

    msg = RaceStrategyEngine.build("Renato", _goal(10.0, "00:50:00"))

    assert msg is not None
    assert "5:00/km" in msg
    assert "Pace-alvo" in msg
    assert "Largada CONTROLADA" in msg


def test_estimates_from_fitness_without_target_time():

    goal = _goal(10.0, target_time=None)

    plan = RaceStrategyEngine.plan(goal, _metrics(threshold=5.5))

    assert plan is not None
    assert plan.estimated is True
    # 5.5 min/km * 10 km = 55 min
    assert plan.total_minutes == 55.0

    msg = RaceStrategyEngine.build("Renato", goal, _metrics(5.5))
    assert "ritmo atual" in msg


def test_none_without_time_and_without_metrics():

    assert RaceStrategyEngine.plan(_goal(10.0, target_time=None)) is None
    assert RaceStrategyEngine.build("R", _goal(10.0, target_time=None)) is None


def test_long_race_gets_fueling():

    msg = RaceStrategyEngine.build("Renato", _goal(21.0975, "01:50:00"))

    assert "gel" in msg.lower() or "carboidrato" in msg.lower()


def test_short_race_no_fueling():

    msg = RaceStrategyEngine.build("Renato", _goal(5.0, "00:25:00"))

    assert "gel" not in msg.lower()


def test_parse_time_formats():

    assert RaceStrategyEngine._parse_time("01:30:00") == 90.0
    assert RaceStrategyEngine._parse_time("50:00") == 50.0
    assert RaceStrategyEngine._parse_time(None) is None
    assert RaceStrategyEngine._parse_time("abc") is None


def test_no_distance_returns_none():

    assert RaceStrategyEngine.plan(_goal(distance_km=0.0)) is None
