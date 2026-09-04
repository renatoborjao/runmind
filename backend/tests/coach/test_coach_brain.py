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
    """Compat: o `action` singular antigo ainda é aceito (vira 1 item)."""

    d = _parse({
        "say": "Movo teu longão pra amanhã, ritmo leve — posso aplicar?",
        "action": {
            "type": "simplify", "scope": "single_session",
            "target_day": "Saturday", "instruction": "ritmo livre, sem pace",
        },
    })

    assert len(d.all_actions) == 1
    a = d.all_actions[0]
    assert a.type == "simplify"
    assert a.scope == "single_session"
    assert a.target_day == "Saturday"
    assert "livre" in a.instruction


def test_parse_goal_action_with_structured_race_fields():
    """Ação goal traz a prova ESTRUTURADA + a hierarquia (relationship), sem
    depender de re-parsear texto."""

    d = _parse({
        "say": "Boa! Registrei tua 15k como degrau rumo aos 21k. 🎯",
        "actions": [{
            "type": "goal", "scope": "single_session", "target_day": None,
            "instruction": "correr a 15k Villa-Lobos em 5:00/km",
            "race_name": "Santander Track&Field - Villa-Lobos",
            "distance_km": 15, "race_date": "2026-12-20",
            "target_time": "1:15:00", "relationship": "stepping_stone",
        }],
    })

    a = d.all_actions[0]
    assert a.type == "goal"
    assert a.race_name == "Santander Track&Field - Villa-Lobos"
    assert a.distance_km == 15.0
    assert a.race_date == "2026-12-20"
    assert a.target_time == "1:15:00"
    assert a.relationship == "stepping_stone"


def test_parse_goal_invalid_relationship_dropped():
    """relationship fora do vocabulário vira None (o executor cai no default)."""

    d = _parse({
        "say": "ok",
        "actions": [{"type": "goal", "instruction": "meta nova",
                     "relationship": "xpto"}],
    })

    assert d.all_actions[0].relationship is None


def test_parse_goal_distance_from_string():
    """distance_km como string ('15' ou '21,1') é normalizada pra float."""

    d = _parse({
        "say": "ok",
        "actions": [{"type": "goal", "instruction": "x", "distance_km": "21,1"}],
    })

    assert d.all_actions[0].distance_km == 21.1


def test_parse_defaults_scope_when_invalid():

    d = _parse({"say": "ok", "actions": [{"type": "move", "scope": "xpto"}]})

    assert d.all_actions[0].scope == "single_session"  # default seguro
    assert d.all_actions[0].target_day is None


def test_parse_action_invalid_type_dropped():

    d = _parse({"say": "ok", "actions": [{"type": "banana"}]})

    assert d.all_actions == []


def test_parse_multiple_actions_kept_in_order():
    """O pente do bug: DUAS trocas numa mensagem viram DUAS ações, na ordem."""

    d = _parse({
        "say": "Movo terça pra quarta e quinta pra sexta — posso aplicar?",
        "actions": [
            {"type": "move", "scope": "single_session",
             "target_day": "Wednesday", "instruction": "terça pra quarta"},
            {"type": "move", "scope": "single_session",
             "target_day": "Friday", "instruction": "quinta pra sexta"},
        ],
    })

    assert len(d.all_actions) == 2
    assert d.all_actions[0].target_day == "Wednesday"
    assert d.all_actions[1].target_day == "Friday"


def test_parse_invalid_items_filtered_from_list():

    d = _parse({
        "say": "ok",
        "actions": [
            {"type": "move", "target_day": "Wednesday"},
            {"type": "banana"},
            "lixo",
        ],
    })

    assert len(d.all_actions) == 1
    assert d.all_actions[0].target_day == "Wednesday"


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
