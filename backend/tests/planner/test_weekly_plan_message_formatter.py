from datetime import date

from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


def _session(day, code, distance, **overrides) -> PlannedSession:

    defaults = dict(
        day=day,
        workout_type=code,
        objective="",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min="6:34",
        target_pace_max="7:10",
    )

    defaults.update(overrides)

    return PlannedSession(**defaults)


def _plan(sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=date(2026, 7, 20),
        sessions=sessions,
    )


def test_format_includes_runner_name_and_week_start():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Tuesday", "EASY", 6.0)]),
    )

    assert "Renato" in text
    assert "20/07" in text


def test_workout_types_are_ptbr_runner_language():

    plan = _plan([
        _session("Tuesday", "EASY", 6.0),
        _session("Thursday", "VO2", 6.5,
                 target_pace_min="5:43", target_pace_max="5:43",
                 notes="5x400m"),
        _session("Saturday", "LONG_RUN", 12.0),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Rodagem leve" in text
    assert "Intervalado" in text
    assert "Longão" in text
    # nada de inglês cru
    assert "Easy Run" not in text
    assert "VO2 Max" not in text
    assert "Long Run" not in text


def test_short_longest_session_is_rodagem_longa_not_longao():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Saturday", "LONG_RUN", 5.1)]),
    )

    assert "Rodagem longa" in text
    assert "Longão" not in text


def test_long_session_over_10km_is_longao():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Saturday", "LONG_RUN", 14.0)]),
    )

    assert "Longão" in text


def test_interval_session_shows_series_and_pace():

    plan = _plan([
        _session("Thursday", "VO2", 6.5,
                 target_pace_min="5:43", target_pace_max="5:43",
                 notes="5x400m"),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Série: 5x400m forte a 5:43/km" in text
    assert "Aquecimento" in text
    assert "Desaquecimento" in text


def test_easy_session_shows_execution_detail():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Tuesday", "EASY", 6.0)]),
    )

    assert "confortáveis" in text
    assert "6:34–7:10/km" in text
    assert "conversar" in text


def test_sessions_in_chronological_order_ptbr():

    plan = _plan([
        _session("Saturday", "LONG_RUN", 12.0),
        _session("Tuesday", "EASY", 6.0),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    tuesday_index = text.index("terça-feira")
    saturday_index = text.index("sábado")

    assert tuesday_index < saturday_index
    assert "Tuesday" not in text
