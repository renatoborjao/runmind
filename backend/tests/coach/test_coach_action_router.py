import json

from app.application.coach.conversation.coach_action_router import (
    CoachActionRouter,
)


def _parse(payload: dict):
    return CoachActionRouter._parse(json.dumps(payload))


def test_parse_move():

    decision = _parse({"action": "move", "long_run_day": None})

    assert decision.action == "move"
    assert decision.long_run_day is None


def test_parse_preference_keeps_valid_day():

    decision = _parse({"action": "preference", "long_run_day": "Sunday"})

    assert decision.action == "preference"
    assert decision.long_run_day == "Sunday"


def test_parse_preference_drops_invalid_day():

    decision = _parse({"action": "preference", "long_run_day": "someday"})

    assert decision.action == "preference"
    assert decision.long_run_day is None


def test_parse_none_action():

    assert _parse({"action": "none"}).action == "none"


def test_parse_unknown_action_returns_none():

    assert _parse({"action": "banana"}) is None


def test_parse_broken_json_returns_none():

    assert CoachActionRouter._parse("{not json") is None


def test_parse_non_dict_returns_none():

    assert CoachActionRouter._parse("[1, 2, 3]") is None
