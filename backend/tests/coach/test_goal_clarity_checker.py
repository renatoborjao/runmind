from datetime import date
from types import SimpleNamespace

from app.application.coach.intelligence.goal_clarity_checker import (
    ACTIONABLE,
    OPEN,
    STALE,
    VAGUE,
    GoalClarityChecker,
    goal_clarity_message,
)
from app.application.use_cases.build_training_goal import BuildTrainingGoal

TODAY = date(2026, 8, 31)


def _runner(goal="saúde", target_race=None, race_date=None, target_time=None):

    return SimpleNamespace(
        name="Hélio", goal=goal, target_race=target_race,
        target_time=target_time, race_date=race_date,
    )


def _assess(runner, memory=None):

    return GoalClarityChecker.assess(
        runner, BuildTrainingGoal.execute(runner), memory, today=TODAY
    )


def test_vague_when_health_goal_no_target():

    c = _assess(_runner(goal="saúde"))

    assert c.verdict == VAGUE
    assert "saúde" in goal_clarity_message("Hélio", c).lower()


def test_vague_message_uses_memory_hint():

    c = _assess(_runner(goal="saúde"), memory=["Foco em prova de 10 km"])

    assert c.verdict == VAGUE
    assert c.latent_distance_hint == "10 km"
    assert "10 km" in goal_clarity_message("Hélio", c)


def test_open_when_distance_but_no_date():

    c = _assess(_runner(goal="correr 21 km, buscar saúde"))

    assert c.verdict == OPEN
    assert goal_clarity_message("Renato", c) == ""


def test_actionable_when_distance_and_future_date():

    c = _assess(_runner(
        goal="10k", target_race="10 km",
        race_date="2026-10-15", target_time="00:50:00",
    ))

    assert c.verdict == ACTIONABLE
    assert goal_clarity_message("Ana", c) == ""


def test_stale_when_race_date_already_passed():
    """Hélio real: 10 km com data 15/08 que JÁ passou -> pergunta o próximo."""

    c = _assess(_runner(
        goal="saúde", target_race="10 km", race_date="2026-08-15",
    ))

    assert c.verdict == STALE
    assert c.passed_race_label == "10 km"
    msg = goal_clarity_message("Hélio", c)
    assert "10 km" in msg and "passou" in msg
