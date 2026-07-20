import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.coach.conversation.move_skip_flow import MoveSkipFlow
from app.application.coach.planning.move_skip_engine import MoveSkipRequest
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.move_skip_flow"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("não vou treinar hoje", True),
        ("joga o treino de terça pra quarta", True),
        ("posso pular o treino de amanhã?", True),
        ("vou precisar reprogramar meu longao para amanhã, domingo", True),
        ("como foi meu último treino?", False),
        ("bom dia!", False),
    ],
)
def test_gate_only_fires_on_move_or_skip(text, expected):

    assert MoveSkipFlow._looks_like_move_or_skip(text) is expected


def _session(day) -> PlannedSession:

    return PlannedSession(
        day=day, workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50",
        structure=(
            "Corrida contínua: 9 km em ritmo leve.\n"
            "Dica: você gosta de rodagem leve nesse dia, fique à vontade."
        ),
    )


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=9.0, running_days=["Tuesday", "Thursday"],
        week_start=date(2026, 7, 6),
        sessions=[_session("Tuesday"), _session("Thursday")],
    )


def _run(request, runner=None):

    runner = runner or make_runner()

    repo = MagicMock()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.MoveSkipEngine") as engine,
        patch(f"{MODULE}.PlanProposalRepository", return_value=repo),
    ):

        provider.for_profile = AsyncMock(return_value=(runner, _plan()))
        engine.propose = AsyncMock(return_value=request)

        reply = asyncio.run(
            MoveSkipFlow.handle("renato", runner, "não vou treinar terça")
        )

    return reply, repo


def test_skip_stores_a_drop_operation():

    request = MoveSkipRequest(
        action="skip", day="Tuesday", target_day=None,
        message="Beleza, tiro o treino de terça. Aplico?",
    )

    reply, repo = _run(request)

    assert "Aplico?" in reply

    saved = repo.save.call_args.args[1]
    assert saved.kind == "skip"
    assert saved.operations == [{"action": "drop", "day": "Tuesday"}]


def test_move_stores_drop_plus_replace_on_target():

    request = MoveSkipRequest(
        action="move", day="Tuesday", target_day="Wednesday",
        message="Movo o tiro pra quarta. Aplico?",
    )

    reply, repo = _run(request)

    ops = repo.save.call_args.args[1].operations

    assert ops[0] == {"action": "drop", "day": "Tuesday"}
    assert ops[1]["action"] == "replace"
    assert ops[1]["day"] == "Wednesday"
    assert ops[1]["session"]["day"] == "Wednesday"
    assert ops[1]["session"]["workout_type"] == "Velocidade"
    assert "garmin" not in ops[1]["session"]     # sessão movida nasce limpa

    # Dica presa ao dia original some — pode ter virado contradição
    assert "Dica:" not in ops[1]["session"]["structure"]
    assert "Corrida contínua: 9 km" in ops[1]["session"]["structure"]


def test_external_coach_is_left_alone():

    runner = make_runner(external_coach=True)

    with patch(f"{MODULE}.CurrentPlanProvider") as provider:

        provider.for_profile = AsyncMock()

        reply = asyncio.run(
            MoveSkipFlow.handle("renato", runner, "não vou treinar hoje")
        )

    assert reply is None
    provider.for_profile.assert_not_called()


def test_gate_blocks_before_touching_the_ai():

    runner = make_runner()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.MoveSkipEngine") as engine,
    ):

        provider.for_profile = AsyncMock()
        engine.propose = AsyncMock()

        reply = asyncio.run(
            MoveSkipFlow.handle("renato", runner, "bom dia, tudo certo?")
        )

    assert reply is None
    provider.for_profile.assert_not_called()
    engine.propose.assert_not_called()


def test_no_proposal_when_engine_returns_none():

    reply, repo = _run(None)

    assert reply is None
    repo.save.assert_not_called()
