import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.coach.conversation.aversion_flow import AversionFlow
from app.application.coach.planning.aversion_swap_engine import AversionSwap
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.aversion_flow"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("não curto tiro na pista", True),
        ("odeio subida", True),
        ("pode trocar o fartlek?", True),
        ("como foi meu longão?", False),      # tipo, mas sem pedido de troca
        ("bom dia, tudo certo?", False),
    ],
)
def test_gate_only_fires_on_change_requests(text, expected):

    assert AversionFlow._looks_like_aversion(text) is expected


def _plan() -> TrainingPlan:

    session = PlannedSession(
        day="Tuesday", workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50",
    )

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=9.0, running_days=["Tuesday"],
        week_start=date(2026, 7, 6), sessions=[session],
    )


def _swap() -> AversionSwap:

    return AversionSwap(
        day="Tuesday",
        session={"day": "Tuesday", "workout_type": "Fartlek"},
        message="Troco o tiro por um fartlek na rua, mantém a velocidade. "
                "Aplico?",
    )


def test_handle_proposes_and_stores_the_pending_proposal():

    runner = make_runner()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.AversionSwapEngine") as engine,
        patch(f"{MODULE}.PlanProposalRepository") as repo_cls,
    ):

        provider.for_profile = AsyncMock(return_value=(runner, _plan()))
        engine.propose = AsyncMock(return_value=_swap())

        reply = asyncio.run(
            AversionFlow.handle("renato", runner, "não curto tiro na pista")
        )

    assert "Aplico?" in reply

    saved = repo_cls.return_value.save.call_args.args[1]
    assert saved.kind == "aversion"
    assert saved.week_start == "2026-07-06"
    assert saved.operations[0]["action"] == "replace"
    assert saved.operations[0]["day"] == "Tuesday"


def test_gate_blocks_before_touching_the_ai():

    runner = make_runner()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.AversionSwapEngine") as engine,
    ):

        provider.for_profile = AsyncMock()
        engine.propose = AsyncMock()

        reply = asyncio.run(
            AversionFlow.handle("renato", runner, "bom dia, tudo certo?")
        )

    assert reply is None
    provider.for_profile.assert_not_called()
    engine.propose.assert_not_called()


def test_external_coach_is_left_alone():

    runner = make_runner(external_coach=True)

    with patch(f"{MODULE}.CurrentPlanProvider") as provider:

        provider.for_profile = AsyncMock()

        reply = asyncio.run(
            AversionFlow.handle("renato", runner, "não curto tiro na pista")
        )

    assert reply is None
    provider.for_profile.assert_not_called()


def test_no_proposal_when_ai_finds_no_aversion():

    runner = make_runner()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.AversionSwapEngine") as engine,
        patch(f"{MODULE}.PlanProposalRepository") as repo_cls,
    ):

        provider.for_profile = AsyncMock(return_value=(runner, _plan()))
        engine.propose = AsyncMock(return_value=None)

        reply = asyncio.run(
            AversionFlow.handle("renato", runner, "não curto tiro")
        )

    assert reply is None
    repo_cls.return_value.save.assert_not_called()
