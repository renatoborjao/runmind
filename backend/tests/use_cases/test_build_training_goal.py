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

    # texto sem número nem prova nomeada cai no default
    assert BuildTrainingGoal.execute(
        make_runner(target_race="corrida de rua"),
    ).distance_km == 10.0


def test_named_distances_without_number():
    """Provas nomeadas sem número viram a distância oficial."""

    assert BuildTrainingGoal.execute(
        make_runner(target_race="meia maratona"),
    ).distance_km == 21.0975

    assert BuildTrainingGoal.execute(
        make_runner(target_race="maratona"),
    ).distance_km == 42.195


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


def test_race_label_names_the_race_not_the_aspiration():
    """race_label descreve a PROVA (distância), separado do objetivo de fundo
    (name). É o que impede 'polimento pra 21km' numa prova de 10k."""

    goal = BuildTrainingGoal.execute(
        make_runner(
            goal="correr 21 km, buscar saúde/evolução",
            target_race="10 km",
            race_date="2026-08-23",
        )
    )

    assert goal.race_label == "10 km"
    # o objetivo de fundo (name) segue sendo a aspiração — NÃO a prova
    assert "21 km" in goal.name


def test_race_label_named_distances():

    from app.domain.entities.training_goal import TrainingGoal

    def label(km):
        return TrainingGoal(
            name="x", distance_km=km, target_time=None, race_date=None,
        ).race_label

    assert label(21.0975) == "meia maratona"
    assert label(42.195) == "maratona"
    assert label(5.0) == "5 km"
    assert label(10.5) == "10.5 km"
