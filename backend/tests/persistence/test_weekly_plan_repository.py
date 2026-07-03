from datetime import date

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


def _isolated_repo(tmp_path):

    repo = WeeklyPlanRepository()

    repo.storage = tmp_path

    return repo


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
                day="Monday",
                workout_type="Easy Run",
                objective="Base",
                planned_distance_km=8.0,
                planned_duration_minutes=None,
                target_pace_min="5:12",
                target_pace_max="5:48",
                notes="Rodagem leve.",
            ),
        ],
    )


def test_load_returns_none_when_no_file(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.load("renato") is None


def test_save_and_load_round_trip(tmp_path):

    repo = _isolated_repo(tmp_path)

    plan = _plan()

    repo.save("renato", plan)

    loaded = repo.load("renato")

    assert loaded is not None
    assert loaded.athlete_name == "Renato"
    assert loaded.week_start == date(2026, 7, 20)
    assert loaded.running_days == ["Monday", "Wednesday", "Sunday"]
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].workout_type == "Easy Run"
    assert loaded.sessions[0].target_pace_min == "5:12"


def test_save_overwrites_previous_plan(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("renato", _plan())

    updated = _plan()
    updated.weekly_volume = 40.0

    repo.save("renato", updated)

    loaded = repo.load("renato")

    assert loaded.weekly_volume == 40.0
