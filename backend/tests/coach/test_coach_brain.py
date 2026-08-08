import json

from app.application.coach.conversation.coach_brain import CoachBrain


def _parse(payload: dict):
    return CoachBrain._parse(json.dumps(payload))


def test_parse_chat_only():

    d = _parse({"say": "Bora treinar! 👊"})

    assert d.say == "Bora treinar! 👊"
    assert d.answer_card is None
    assert d.action is None
    assert d.on_pending is None


def test_parse_answer_card():

    d = _parse({"say": "Teu plano 👇", "answer_card": "weekly_plan"})

    assert d.answer_card == "weekly_plan"


def test_parse_invalid_card_dropped():

    d = _parse({"say": "oi", "answer_card": "inexistente"})

    assert d.answer_card is None


def test_parse_action_with_scope():

    d = _parse({
        "say": "Movo teu longão pra amanhã, ritmo leve — posso aplicar?",
        "action": {
            "type": "simplify", "scope": "single_session",
            "target_day": "Saturday", "instruction": "ritmo livre, sem pace",
        },
    })

    assert d.action.type == "simplify"
    assert d.action.scope == "single_session"
    assert d.action.target_day == "Saturday"
    assert "livre" in d.action.instruction


def test_parse_action_defaults_scope_when_invalid():

    d = _parse({"say": "ok", "action": {"type": "move", "scope": "xpto"}})

    assert d.action.scope == "single_session"  # default seguro
    assert d.action.target_day is None


def test_parse_action_invalid_type_dropped():

    d = _parse({"say": "ok", "action": {"type": "banana"}})

    assert d.action is None


def test_parse_on_pending():

    d = _parse({"say": "Feito!", "on_pending": "apply"})

    assert d.on_pending == "apply"


def test_parse_on_pending_invalid_dropped():

    d = _parse({"say": "hmm", "on_pending": "talvez"})

    assert d.on_pending is None


def test_parse_empty_decision_returns_none():
    """Sem fala, cartão, ação ou veredito de pendência: nada acionável."""

    assert _parse({"say": "", "action": None}) is None


def test_parse_broken_json_returns_none():

    assert CoachBrain._parse("{quebrado") is None
