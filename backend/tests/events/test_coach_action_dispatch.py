import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.coach_action_router import (
    ActionDecision,
)
from app.application.events.coach_conversation import CoachConversationEvent
from tests.coach.factories import make_runner

MODULE = "app.application.events.coach_conversation"


def _dispatch(decision):

    return asyncio.run(
        CoachConversationEvent._dispatch_action(
            "renato", make_runner(), "mensagem qualquer", decision
        )
    )


def test_move_routes_to_move_skip_flow_forced():

    with patch(f"{MODULE}.MoveSkipFlow.handle", new=AsyncMock(return_value="ok")) as h:

        result = _dispatch(ActionDecision(action="move"))

    assert result == "ok"
    assert h.call_args.kwargs["force"] is True


def test_skip_routes_to_move_skip_flow_forced():

    with patch(f"{MODULE}.MoveSkipFlow.handle", new=AsyncMock(return_value="ok")) as h:

        _dispatch(ActionDecision(action="skip"))

    assert h.call_args.kwargs["force"] is True


def test_adjust_routes_to_negotiation_forced():

    with patch(f"{MODULE}.NegotiationFlow.handle", new=AsyncMock(return_value="ok")) as h:

        assert _dispatch(ActionDecision(action="adjust")) == "ok"
        assert h.call_args.kwargs["force"] is True


def test_aversion_routes_to_aversion_forced():

    with patch(f"{MODULE}.AversionFlow.handle", new=AsyncMock(return_value="ok")) as h:

        assert _dispatch(ActionDecision(action="aversion")) == "ok"
        assert h.call_args.kwargs["force"] is True


def test_one_off_routes_forced():

    with patch(f"{MODULE}.OneOffWorkoutFlow.handle", new=AsyncMock(return_value="ok")) as h:

        assert _dispatch(ActionDecision(action="one_off")) == "ok"
        assert h.call_args.kwargs["force"] is True


def test_goal_routes_forced():

    with patch(f"{MODULE}.GoalChangeApplier.handle", new=AsyncMock(return_value="ok")) as h:

        assert _dispatch(ActionDecision(action="goal")) == "ok"
        assert h.call_args.kwargs["force"] is True


def test_preference_with_day_applies_long_run_preference():

    with patch(
        f"{MODULE}.PlanPreferenceApplier.apply", new=AsyncMock(return_value="ok")
    ) as h:

        result = _dispatch(
            ActionDecision(action="preference", long_run_day="Sunday")
        )

    assert result == "ok"
    # o applier recebe a PlanPreference com o dia certo
    pref = h.call_args.args[2]
    assert pref.long_run_day == "Sunday"


def test_preference_without_day_does_nothing():
    """Sem dia resolvido, não aplica preferência (cai na cascata)."""

    assert _dispatch(ActionDecision(action="preference", long_run_day=None)) is None
