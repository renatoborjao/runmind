from datetime import date, datetime

from app.application.planner.missed_workout_detector import (
    MissedWorkoutDetector,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

WEEK = date(2026, 7, 6)      # segunda
WEDNESDAY = date(2026, 7, 8)  # referência -> ontem = terça 07/07


def _session(day, kind="run") -> PlannedSession:

    return PlannedSession(
        day=day, workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50", kind=kind,
    )


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=0.0, running_days=[s.day for s in sessions],
        week_start=WEEK, sessions=list(sessions),
    )


def test_missed_when_planned_yesterday_and_no_activity():

    missed = MissedWorkoutDetector.yesterday_missed(
        _plan(_session("Tuesday")), [], WEDNESDAY,
    )

    assert missed is not None
    assert missed.day == "Tuesday"


def test_not_missed_when_an_activity_fulfilled_it():

    act = make_activity(
        id=1, start_date=datetime(2026, 7, 7, 7, 0), distance=9000.0,
    )

    missed = MissedWorkoutDetector.yesterday_missed(
        _plan(_session("Tuesday")), [act], WEDNESDAY,
    )

    assert missed is None


def test_rest_day_yesterday_is_not_a_miss():

    # nada planejado na terça (só quinta) -> ontem foi descanso
    missed = MissedWorkoutDetector.yesterday_missed(
        _plan(_session("Thursday")), [], WEDNESDAY,
    )

    assert missed is None


def test_yesterday_outside_this_plan_week_is_ignored():

    # referência = segunda 06/07 -> ontem = domingo 05/07, semana passada
    missed = MissedWorkoutDetector.yesterday_missed(
        _plan(_session("Tuesday")), [], date(2026, 7, 6),
    )

    assert missed is None


def test_non_running_session_is_not_cobranca():

    missed = MissedWorkoutDetector.yesterday_missed(
        _plan(_session("Tuesday", kind="strength")), [], WEDNESDAY,
    )

    assert missed is None
