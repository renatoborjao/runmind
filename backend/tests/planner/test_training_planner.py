from datetime import date

from app.application.planner.planner import TrainingPlanner
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from tests.coach.factories import make_runner

WEEK_START = date(2026, 7, 20)


def _assessment(**overrides) -> TrainingAssessment:

    defaults = dict(
        level="Intermediate",
        current_weekly_volume=30.0,
        recommended_weekly_volume=32.4,
        consistency=80.0,
        longest_run=12.0,
        available_training_days=3,
        goal="10k",
        observations=[],
    )

    defaults.update(overrides)

    return TrainingAssessment(**defaults)


def _metrics(**overrides) -> RunnerMetrics:

    defaults = dict(
        easy_pace_min=5.20,
        easy_pace_max=5.80,
        threshold_pace=4.85,
        vo2_pace=4.35,
        average_hr=150.0,
        max_long_run=15.0,
        weekly_volume=30.0,
        consistency=80.0,
    )

    defaults.update(overrides)

    return RunnerMetrics(**defaults)


def _goal() -> TrainingGoal:

    return TrainingGoal(
        name="10k",
        distance_km=10,
        target_time="50:00",
        race_date=None,
    )


def test_generate_fills_real_pace_on_all_sessions():

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    for session in plan.sessions:

        assert session.target_pace_min is not None
        assert session.target_pace_max is not None

    easy = plan.sessions[0]

    assert easy.target_pace_min == "5:12"
    assert easy.target_pace_max == "5:48"

    vo2 = plan.sessions[1]

    assert vo2.target_pace_min == vo2.target_pace_max == "4:21"

    long = plan.sessions[2]

    assert long.target_pace_min == easy.target_pace_min
    assert long.target_pace_max == easy.target_pace_max


def test_generate_sets_week_start_on_plan():

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    assert plan.week_start == WEEK_START
