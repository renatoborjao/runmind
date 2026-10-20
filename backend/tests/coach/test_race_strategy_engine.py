from datetime import date
from unittest.mock import patch

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal


def _goal(distance_km=10.0, target_time="00:50:00", race_date=None):
    return TrainingGoal(
        name="10k sub-50",
        distance_km=distance_km,
        target_time=target_time,
        race_date=race_date or date(2026, 8, 23),
    )


def _metrics(threshold=5.5):
    return RunnerMetrics(
        easy_pace_min=6.0, easy_pace_max=6.5, threshold_pace=threshold,
        vo2_pace=4.5, average_hr=150.0, max_long_run=16.0, weekly_volume=30.0,
    )


def test_plan_from_target_time():

    plan = RaceStrategyEngine.plan(_goal(10.0, "00:50:00"))

    assert plan is not None
    assert plan.estimated is False
    assert plan.total_minutes == 50.0
    assert plan.avg_pace_min == 5.0
    # abre ~5s mais devagar, fecha ~5s mais forte
    assert plan.open_pace_min > plan.avg_pace_min > plan.close_pace_min
    # passagem na metade correndo a 1a metade controlada (~25 min +)
    assert 25.0 < plan.halfway_minutes < 26.5


def test_message_has_pace_and_splits():

    msg = RaceStrategyEngine.build("Renato", _goal(10.0, "00:50:00"))

    assert msg is not None
    assert "5:00/km" in msg
    assert "Pace-alvo" in msg
    assert "Largada CONTROLADA" in msg


def test_estimates_from_fitness_without_target_time():

    goal = _goal(10.0, target_time=None)

    plan = RaceStrategyEngine.plan(goal, _metrics(threshold=5.5))

    assert plan is not None
    assert plan.estimated is True
    # 5.5 min/km * 10 km = 55 min
    assert plan.total_minutes == 55.0

    msg = RaceStrategyEngine.build("Renato", goal, _metrics(5.5))
    assert "ritmo atual" in msg


def test_none_without_time_and_without_metrics():

    assert RaceStrategyEngine.plan(_goal(10.0, target_time=None)) is None
    assert RaceStrategyEngine.build("R", _goal(10.0, target_time=None)) is None


def test_long_race_gets_fueling():

    msg = RaceStrategyEngine.build("Renato", _goal(21.0975, "01:50:00"))

    assert "gel" in msg.lower() or "carboidrato" in msg.lower()


def test_short_race_no_fueling():

    msg = RaceStrategyEngine.build("Renato", _goal(5.0, "00:25:00"))

    assert "gel" not in msg.lower()


# ---- nutrição do dia da prova = a MESMA do plano dos longões ---------------------------
# Antes a estratégia tinha uma linha própria por DISTÂNCIA (>= 15 km: "a cada ~40-45 min"),
# que contradizia o advisor dos treinos (duração; 35 min) e ignorava as restrições.

REPO = "app.infrastructure.persistence.nutrition_repository.NutritionRepository.load"


def _no_restrictions():

    return patch(REPO, return_value={"settings": {}})


def test_a_fast_15k_gets_no_gel_unlike_the_old_distance_rule():
    """15 km em 1h05: abaixo de 75 min repor carboidrato não muda nada — a regra antiga
    por distância mandava tomar gel mesmo assim."""

    msg = RaceStrategyEngine.build("Renato", _goal(15.0, "01:05:00"))

    assert "Nutrição na prova" not in msg
    assert "gel" not in msg.lower()


def test_a_15k_in_82_minutes_gets_one_optional_gel():
    """Maurício, 15 km em 1:22:30: 75–94 min = 1 gel opcional perto da metade."""

    with _no_restrictions():

        msg = RaceStrategyEngine.build(
            "Mauricio", _goal(15.0, "01:22:30"), profile="mauricio",
        )

    assert "Nutrição na prova (opcional): 1 gel (~25 g de carboidrato) aos 40 min" in msg
    assert "Sem gel: 2 balas de goma, 1 banana ou isotônico" in msg
    assert "Dica: programe no relógio um alerta de tempo aos 40 min" in msg
    assert "nada novo no dia da prova" in msg
    assert "Hidrate desde cedo" in msg


def test_a_half_marathon_follows_the_same_schedule_as_the_long_runs():
    """110 min: gel aos 35 e 70 — o mesmo cronograma e a mesma dica do plano dos
    longões (antes o cartão dizia 'a cada ~40-45 min')."""

    from app.application.planner.fueling_advisor import schedule

    assert schedule(110) == [35, 70]

    with _no_restrictions():

        msg = RaceStrategyEngine.build(
            "Renato", _goal(21.0975, "01:50:00"), profile="renato2",
        )

    assert "Nutrição na prova: gel (~25 g de carboidrato) aos 35 e 70 min" in msg
    assert "alerta de tempo que repita a cada 35 min" in msg
    assert "40-45" not in msg


def test_diabetes_gets_the_referral_in_the_race_too():

    with patch(REPO, return_value={"settings": {"restrictions": "Diabetes tipo 1"}}):

        msg = RaceStrategyEngine.build(
            "Renato", _goal(21.0975, "01:50:00"), profile="p",
        )

    assert "combine com seu médico ou nutricionista" in msg
    assert "aos 35" not in msg and "gel (~25 g" not in msg


def test_someone_who_dislikes_gel_gets_the_alternatives_in_the_race_too():

    with patch(REPO, return_value={"settings": {"dislikes": "não curto gel"}}):

        msg = RaceStrategyEngine.build(
            "Renato", _goal(21.0975, "01:50:00"), profile="p",
        )

    assert "como você não curte gel" in msg
    assert "2 balas de goma, 1 banana ou isotônico" in msg


def test_a_failure_in_the_nutrition_never_breaks_the_strategy():

    with patch(
        "app.application.planner.fueling_advisor.race_fueling_lines",
        side_effect=RuntimeError("boom"),
    ):

        msg = RaceStrategyEngine.build("Renato", _goal(21.0975, "01:50:00"))

    assert "Pace-alvo" in msg
    assert "Nutrição na prova" not in msg


def test_the_chat_passes_the_profile_so_the_restrictions_apply():
    """O atleta pede a estratégia no chat: o slug segue até a nutrição."""

    import inspect

    from app.application.coach.conversation import on_demand_answers

    source = inspect.getsource(on_demand_answers)

    assert "runner.name, goal, metrics, profile=profile" in source


def test_parse_time_formats():

    assert RaceStrategyEngine._parse_time("01:30:00") == 90.0
    assert RaceStrategyEngine._parse_time("50:00") == 50.0
    assert RaceStrategyEngine._parse_time(None) is None
    assert RaceStrategyEngine._parse_time("abc") is None


def test_no_distance_returns_none():

    assert RaceStrategyEngine.plan(_goal(distance_km=0.0)) is None
