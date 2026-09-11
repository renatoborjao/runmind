from datetime import date

from app.application.coach.planning.race_hierarchy_directive import (
    race_hierarchy_directive,
)
from app.domain.entities.training_goal import TrainingGoal


def _goal(distance_km=15.0, target_time="1:15:00", race_date="2026-12-20"):

    return TrainingGoal(
        name="correr 21 km, buscar saúde/evolução e correr mais rápido",
        distance_km=distance_km,
        target_time=target_time,
        race_date=date.fromisoformat(race_date) if race_date else None,
    )


# o objetivo de fundo do renato2 (21 km)
_BG = "correr 21 km, buscar saúde/evolução e correr mais rápido"


def test_checkpoint_when_background_is_longer():
    # fundo 21k, prova próxima 15k → 15k é checkpoint rumo ao 21k
    out = race_hierarchy_directive(_goal(), _BG)

    assert "CHECKPOINT" in out
    assert "meia maratona" in out          # fundo 21k
    assert "15 km" in out                  # a prova próxima
    assert "mira 1:15:00" in out           # meta do checkpoint
    assert "não encerre o ciclo" in out
    assert "não decreto" in out            # é insumo


def test_empty_when_next_race_is_the_background_distance():
    # prova próxima JÁ é 21k → é o alvo, não checkpoint
    out = race_hierarchy_directive(_goal(distance_km=21.0), _BG)

    assert out == ""


def test_empty_without_dated_race():
    out = race_hierarchy_directive(_goal(race_date=None), _BG)

    assert out == ""


def test_empty_when_background_not_longer():
    # fundo 10k, prova próxima 15k → fundo não é mais longo
    out = race_hierarchy_directive(_goal(), "correr 10 km com saúde")

    assert out == ""


def test_without_target_time_still_frames_checkpoint():
    out = race_hierarchy_directive(_goal(target_time=None), _BG)

    assert "CHECKPOINT" in out
    assert "mira" not in out  # sem meta explícita do checkpoint
