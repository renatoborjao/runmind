from datetime import date

from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Monday", "Wednesday", "Sunday"],
        week_start=date(2026, 7, 20),
        sessions=[
            PlannedSession(
                day="Sunday",
                workout_type="Long Run",
                objective="Resistência",
                planned_distance_km=15.0,
                planned_duration_minutes=None,
                target_pace_min="5:12",
                target_pace_max="5:48",
            ),
            PlannedSession(
                day="Monday",
                workout_type="Easy Run",
                objective="Base",
                planned_distance_km=8.0,
                planned_duration_minutes=None,
                target_pace_min="5:12",
                target_pace_max="5:48",
            ),
        ],
    )


def test_format_includes_runner_name_and_week_start():

    text = WeeklyPlanMessageFormatter.format("Renato", _plan())

    assert "Renato" in text
    assert "20/07" in text


def test_format_lists_sessions_in_chronological_order():

    text = WeeklyPlanMessageFormatter.format("Renato", _plan())

    monday_index = text.index("Monday")
    sunday_index = text.index("Sunday")

    assert monday_index < sunday_index


def test_format_includes_pace_and_distance():

    text = WeeklyPlanMessageFormatter.format("Renato", _plan())

    assert "5:12-5:48 min/km" in text
    assert "8.0 km" in text
    assert "15.0 km" in text
