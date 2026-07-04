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


def test_generate_with_two_days_builds_easy_and_long():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Saturday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    assert len(plan.sessions) == 2

    easy, long = plan.sessions

    assert easy.day == "Tuesday"
    assert long.day == "Saturday"

    # volume da semana preservado nas duas sessões
    total = (easy.planned_distance_km or 0) + (
        long.planned_distance_km or 0
    )
    assert abs(total - _assessment().recommended_weekly_volume) < 0.2


def test_generate_with_one_day_builds_single_session():

    runner = make_runner(
        preferred_running_days=["Sunday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    assert len(plan.sessions) == 1
    assert plan.sessions[0].day == "Sunday"
    assert plan.sessions[0].planned_distance_km == (
        _assessment().recommended_weekly_volume
    )


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


def test_taper_phase_reduces_weekly_volume():

    from unittest.mock import patch

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    with patch(
        "app.application.planner.planner.PhaseEngine"
    ) as mock_phase:

        mock_phase.execute.return_value = "TAPER"

        plan = TrainingPlanner.generate(
            runner,
            _assessment(),
            _goal(),
            _metrics(),
            WEEK_START,
        )

    assert plan.phase == "TAPER"

    total = sum(
        session.planned_distance_km or 0
        for session in plan.sessions
    )

    # 32.4 * 0.6 = 19.4 (volume de véspera de prova)
    assert abs(total - 19.4) < 0.3


def test_intermediate_gets_vo2_quality_session():

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(level="Intermediate"),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    codes = [s.workout_type for s in plan.sessions]
    assert "VO2" in codes
    assert "PROGRESSION" not in codes

    vo2 = next(s for s in plan.sessions if s.workout_type == "VO2")
    # série escala com a distância (tiros de 400m), não fixa em 6x800
    assert vo2.notes.endswith("x400m")


def test_beginner_gets_progression_not_vo2():

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    plan = TrainingPlanner.generate(
        runner,
        _assessment(level="Beginner"),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    codes = [s.workout_type for s in plan.sessions]
    assert "PROGRESSION" in codes
    assert "VO2" not in codes


def test_long_run_respects_capacity_not_only_weekly_volume():

    runner = make_runner(
        preferred_running_days=["Monday", "Wednesday", "Sunday"],
    )

    # volume baixo (14.6) mas já correu 12 km — longão não deve ficar
    # preso em 35% do volume (~5 km)
    plan = TrainingPlanner.generate(
        runner,
        _assessment(
            recommended_weekly_volume=14.6,
            longest_run=12.0,
        ),
        _goal(),
        _metrics(),
        WEEK_START,
    )

    long = next(s for s in plan.sessions if s.workout_type == "LONG_RUN")
    assert long.planned_distance_km >= 8.0
