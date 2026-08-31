from types import SimpleNamespace

from app.application.coach.intelligence.goal_clarity_checker import (
    ACTIONABLE,
    OPEN,
    VAGUE,
    GoalClarityChecker,
    goal_clarity_message,
)
from app.application.use_cases.build_training_goal import BuildTrainingGoal


def _runner(goal="saúde", target_race=None):

    return SimpleNamespace(
        name="Hélio", goal=goal, target_race=target_race,
        target_time=None, race_date=None,
    )


def _goal(runner):

    return BuildTrainingGoal.execute(runner)


def test_vague_when_health_goal_no_target():
    """Hélio: 'saúde', sem prova/distância -> vaga."""

    r = _runner(goal="saúde")

    c = GoalClarityChecker.assess(r, _goal(r))

    assert c.verdict == VAGUE
    assert "saúde" in goal_clarity_message("Hélio", c).lower()


def test_vague_message_uses_memory_hint():
    """Memória diz 'prova de 10 km' -> a pergunta cita o 10k."""

    r = _runner(goal="saúde")

    c = GoalClarityChecker.assess(
        r, _goal(r), memory_objectives=["Foco em prova de 10 km"]
    )

    assert c.verdict == VAGUE
    assert c.latent_distance_hint == "10 km"
    assert "10 km" in goal_clarity_message("Hélio", c)


def test_open_when_distance_but_no_date():
    """'correr 21 km' sem data -> open (progressão contínua), NÃO cutuca."""

    r = _runner(goal="correr 21 km, buscar saúde")

    c = GoalClarityChecker.assess(r, _goal(r))

    assert c.verdict == OPEN
    assert goal_clarity_message("Renato", c) == ""


def test_actionable_when_distance_and_date():

    r = SimpleNamespace(
        name="Ana", goal="10k", target_race="10 km",
        target_time="00:50:00", race_date="2026-10-15",
    )

    c = GoalClarityChecker.assess(r, BuildTrainingGoal.execute(r))

    assert c.verdict == ACTIONABLE
    assert goal_clarity_message("Ana", c) == ""
