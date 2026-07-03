from datetime import date

from app.application.planner.engines.phase_engine import PhaseEngine
from app.domain.entities.training_goal import TrainingGoal

REFERENCE = date(2026, 7, 3)


def _goal(race_date: date | None) -> TrainingGoal:

    return TrainingGoal(
        name="10k",
        distance_km=10.0,
        target_time="00:50:00",
        race_date=race_date,
    )


def test_no_race_is_continuous_build():

    assert PhaseEngine.execute(_goal(None), REFERENCE) == "BUILD"


def test_far_race_is_base():

    # 12 semanas até a prova
    assert PhaseEngine.execute(
        _goal(date(2026, 9, 25)),
        REFERENCE,
    ) == "BASE"


def test_mid_range_race_is_build():

    # ~6 semanas até a prova (caso real do Renato: prova em agosto)
    assert PhaseEngine.execute(
        _goal(date(2026, 8, 15)),
        REFERENCE,
    ) == "BUILD"


def test_race_week_is_taper():

    # 1 semana até a prova
    assert PhaseEngine.execute(
        _goal(date(2026, 7, 10)),
        REFERENCE,
    ) == "TAPER"


def test_past_race_falls_back_to_build():

    assert PhaseEngine.execute(
        _goal(date(2026, 6, 1)),
        REFERENCE,
    ) == "BUILD"


def test_race_today_is_not_a_target_anymore():

    assert PhaseEngine.execute(
        _goal(REFERENCE),
        REFERENCE,
    ) == "BUILD"
