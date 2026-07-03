from datetime import date

from app.application.use_cases.build_training_goal import BuildTrainingGoal
from tests.coach.factories import make_runner


def test_distance_parsed_from_target_race():

    goal = BuildTrainingGoal.execute(
        make_runner(target_race="10 km"),
    )

    assert goal.distance_km == 10.0


def test_distance_parses_compact_and_decimal_formats():

    assert BuildTrainingGoal.execute(
        make_runner(target_race="21k"),
    ).distance_km == 21.0

    assert BuildTrainingGoal.execute(
        make_runner(target_race="prova de 5,5 km"),
    ).distance_km == 5.5


def test_distance_defaults_without_number():

    assert BuildTrainingGoal.execute(
        make_runner(target_race=None),
    ).distance_km == 10.0

    assert BuildTrainingGoal.execute(
        make_runner(target_race="maratona"),
    ).distance_km == 10.0


def test_race_date_parsed_when_present():

    goal = BuildTrainingGoal.execute(
        make_runner(race_date="2026-08-15"),
    )

    assert goal.race_date == date(2026, 8, 15)


def test_race_date_none_without_race_or_invalid():

    assert BuildTrainingGoal.execute(
        make_runner(),
    ).race_date is None

    assert BuildTrainingGoal.execute(
        make_runner(race_date="agosto"),
    ).race_date is None
