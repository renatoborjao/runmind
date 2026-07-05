from datetime import date

from app.application.planner.engines.run_walk_engine import RunWalkEngine
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

WEEK_START = date(2026, 7, 6)  # segunda


def _plan(sessions):

    return TrainingPlan(
        athlete_name="Adolfo",
        objective="Saúde",
        phase="BASE",
        weekly_volume=0.0,
        running_days=[s.day for s in sessions],
        week_start=WEEK_START,
        sessions=sessions,
    )


def _text(runner, days):

    plan = _plan(RunWalkEngine.build(days, 1, runner))

    return "\n".join(WeeklyPlanMessageFormatter.session_lines(plan))


def test_run_walk_block_renders_intervals_and_minutes():

    runner = make_runner(mobility="run_walker")

    text = _text(runner, ["Monday"])

    assert "Corrida-caminhada · 28 min" in text
    assert "5x (trote 30s" in text
    assert "caminhada 3 min)" in text
    # medido em tempo: nunca aparece "0.0 km" (distância None)
    assert "0.0 km" not in text


def test_walk_block_renders_duration_and_pace():

    runner = make_runner(
        mobility="walker", walk_pace_min_km=round(60 / 5.5, 2),
    )

    text = _text(runner, ["Tuesday", "Thursday", "Saturday", "Sunday"])

    assert "Caminhada · 25 min" in text
    assert "25 min de caminhada em ritmo confortável (~10:55/km)" in text


def test_duration_helper_formats_seconds():

    fmt = WeeklyPlanMessageFormatter._duration

    assert fmt(30) == "30s"
    assert fmt(60) == "1 min"
    assert fmt(90) == "1min30"
    assert fmt(180) == "3 min"
