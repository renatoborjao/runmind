"""O coach ENTENDE o que o atleta muda — e executa tudo, sem prometer à toa.

Caso real (João, 05-07/09): "o objetivo é correr 5km em 23 minutos. Tenho
disponibilidade pra correr de segunda, quinta e sábado". O cérebro emitiu meta +
rotina, o executor rodou só a 1ª ação, os dias sumiram, o objetivo principal não
mudou, e o coach prometeu "já estou preparando, em instantes te envio" sem nada
chegar."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import BrainAction, CoachBrain
from app.application.coach.conversation.coach_brain_executor import (
    CoachBrainExecutor,
)
from app.application.coach.conversation.goal_action_executor import (
    GoalActionExecutor,
)
from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

EXECUTOR = "app.application.coach.conversation.coach_brain_executor"


def _action(**kw) -> BrainAction:

    base = dict(type="goal", scope="single_session", target_day=None, instruction="")

    base.update(kw)

    return BrainAction(**base)


# ---- cérebro -------------------------------------------------------------


def test_brain_reads_days_and_replan():

    decision = CoachBrain._parse(
        '{"say": "Fechado!", "actions": ['
        '{"type": "goal", "instruction": "correr 5 km em 23 minutos", '
        '"relationship": "replace", "distance_km": 5, "target_time": "00:23:00"},'
        '{"type": "days", "days": ["saturday", "Monday", "thursday", "Monday"]},'
        '{"type": "replan"}]}'
    )

    goal, days, replan = decision.actions

    assert goal.relationship == "replace" and goal.target_time == "00:23:00"
    assert days.days == ["Monday", "Thursday", "Saturday"]
    assert replan.type == "replan"


def test_brain_prompt_forbids_empty_promises():

    from app.application.coach.conversation.coach_brain import PROMPT_TEMPLATE

    assert "NUNCA PROMETA" in PROMPT_TEMPLATE
    assert '"o objetivo é X"' in PROMPT_TEMPLATE


# ---- executor: TODAS as ações da mensagem --------------------------------


def test_mixed_message_executes_goal_days_and_replan_in_order():

    calls = []

    async def goals(profile, runner, actions, say="", regenerate=True):

        calls.append(("goal", say, regenerate))

        return f"{say} (meta)"

    def days(profile, runner, action, replan_follows=False):

        calls.append(("days", replan_follows))

        return "📅 dias"

    async def replan(profile, runner):

        calls.append(("replan",))

        return "semana refeita"

    actions = [
        _action(type="goal", instruction="correr 5 km em 23 minutos"),
        _action(type="days", days=["Monday", "Thursday", "Saturday"]),
        _action(type="replan"),
    ]

    with (
        patch.object(CoachBrainExecutor, "_goals", side_effect=goals),
        patch.object(CoachBrainExecutor, "_days", side_effect=days),
        patch.object(CoachBrainExecutor, "_replan", side_effect=replan),
    ):

        reply = asyncio.run(
            CoachBrainExecutor._act_all(
                "joao", make_runner(), actions, MagicMock(), "msg", "", "Show!",
            )
        )

    assert [c[0] for c in calls] == ["goal", "days", "replan"]
    assert calls[0] == ("goal", "Show!", False)  # a semana é refeita UMA vez
    assert calls[1] == ("days", True)  # replan vem: sem "a semana segue"
    assert reply.startswith("Show! (meta)")
    assert "📅 dias" in reply and "semana refeita" in reply


def test_days_action_updates_the_profile_the_plan_uses():

    repo = MagicMock()

    runner = make_runner(preferred_running_days=["Tuesday", "Saturday"])

    with (
        patch(f"{EXECUTOR}.RunnerProfileRepository", return_value=repo),
        patch(
            "app.application.coach.memory.runner_memory_service."
            "RunnerMemoryService.process"
        ) as memory,
    ):

        reply = CoachBrainExecutor._days(
            "joao", runner,
            _action(type="days", days=["Monday", "Thursday", "Saturday"]),
        )

    repo.update_fields.assert_called_once_with(
        "joao",
        {
            "preferred_running_days": ["Monday", "Thursday", "Saturday"],
            "weekly_training_days": 3,
        },
    )
    assert runner.preferred_running_days == ["Monday", "Thursday", "Saturday"]
    assert "segunda-feira, quinta-feira, sábado (3x/semana)" in reply
    assert "refaça esta semana" in reply
    memory.assert_called_once()


def test_replan_delivers_the_plan_now():

    runner = make_runner()

    plan = MagicMock()

    with (
        patch(
            "app.application.planner.current_plan_provider.CurrentPlanProvider."
            "for_profile",
            new=AsyncMock(return_value=(runner, plan)),
        ) as provider,
        patch(
            "app.application.planner.weekly_plan_message_formatter."
            "WeeklyPlanMessageFormatter.week_plan_message",
            return_value="PLANO NOVO",
        ),
        patch(
            "app.application.garmin.watch_offer.watch_update_offer",
            return_value=" [relógio?]",
        ),
    ):

        reply = asyncio.run(CoachBrainExecutor._replan("joao", runner))

    provider.assert_awaited_once_with("joao", force=True)
    assert "PLANO NOVO" in reply and "[relógio?]" in reply


def test_replan_is_not_for_external_coach():

    assert asyncio.run(
        CoachBrainExecutor._replan("x", make_runner(external_coach=True))
    ) is None


# ---- meta com tempo, sem prova --------------------------------------------


def test_open_goal_with_time_becomes_the_profile_target():

    repo = MagicMock()

    runner = make_runner()

    runner.race_date = None

    GoalActionExecutor._set_open_target(
        repo, "joao", runner,
        _action(distance_km=5.0, target_time="00:23:00"),
    )

    repo.update_fields.assert_called_once_with(
        "joao",
        {"target_time": "00:23:00", "target_race": "5 km", "race_date": None},
    )


def test_open_goal_does_not_override_a_future_race_anchor():

    repo = MagicMock()

    runner = make_runner()

    runner.race_date = (date.today() + timedelta(days=60)).isoformat()

    GoalActionExecutor._set_open_target(
        repo, "renato", runner,
        _action(distance_km=5.0, target_time="00:23:00"),
    )

    repo.update_fields.assert_not_called()


def test_goal_line_shows_target_pace_without_race():

    goal = TrainingGoal(
        name="correr 5 km em 23 minutos", distance_km=5.0,
        target_time="00:23:00", race_date=None,
    )

    line = PlanContextBuilder._goal_line(goal, None, None)

    assert "alvo 00:23:00 nos 5 km (~4:36/km)" in line


# ---- refazer no meio da semana preserva o que passou ----------------------


def _session(day, kind="Rodagem"):

    return PlannedSession(
        day=day, workout_type=kind, objective="x", planned_distance_km=6.0,
        planned_duration_minutes=None, target_pace_min=None,
        target_pace_max=None,
    )


def _plan(sessions, week_start):

    return TrainingPlan(
        athlete_name="J", objective="5k", phase="BUILD", weekly_volume=18,
        running_days=[s.day for s in sessions], week_start=week_start,
        sessions=sessions,
    )


def test_midweek_replan_keeps_past_days_and_rebuilds_the_rest():

    week = date(2026, 9, 21)  # segunda

    old = _plan(
        [_session("Tuesday", "Tiro"), _session("Saturday", "Longão")], week,
    )

    new = _plan(
        [
            _session("Monday", "NOVO passado"),
            _session("Thursday", "NOVO qui"),
            _session("Saturday", "NOVO sáb"),
        ],
        week,
    )

    with (
        patch(
            "app.application.coach.planning.ai_plan_service.today_local",
            return_value=date(2026, 9, 24),  # quinta
        ),
        patch(
            "app.application.planner.weekly_plan_matcher.WeeklyPlanMatcher."
            "fulfilled_days",
            return_value={"Tuesday"},
        ),
    ):

        AIPlanService._keep_past_days(old, new, TrainingHistory(activities=[]))

    assert [(s.day, s.workout_type) for s in new.sessions] == [
        ("Tuesday", "Tiro"),       # o que passou fica
        ("Thursday", "NOVO qui"),  # o que falta vem da IA
        ("Saturday", "NOVO sáb"),
    ]


def test_context_tells_the_ai_the_week_already_started():

    ctx = PlanContextBuilder.build(
        runner=make_runner(preferred_running_days=["Monday", "Thursday"]),
        goal=TrainingGoal(name="5k", distance_km=5.0, target_time=None, race_date=None),
        week_start=date(2026, 9, 21),
        today=date(2026, 9, 24),
    )

    assert "A SEMANA JÁ COMEÇOU" in ctx and "24/09" in ctx
