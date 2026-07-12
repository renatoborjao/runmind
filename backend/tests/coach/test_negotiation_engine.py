import json
from datetime import date

from app.application.coach.planning.negotiation_engine import NegotiationEngine
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


def _session(day, wtype, dist, kind="run") -> PlannedSession:
    return PlannedSession(
        day=day, workout_type=wtype, objective="",
        planned_distance_km=dist, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None, kind=kind,
    )


def _plan() -> TrainingPlan:
    return TrainingPlan(
        athlete_name="Renato", objective="10k sub-50", phase="BUILD",
        weekly_volume=28.0,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=date(2026, 7, 13),
        sessions=[
            _session("Tuesday", "VO2", 8.0),
            _session("Thursday", "Tempo", 8.0),
            _session("Saturday", "Longão", 12.0),
        ],
    )


def _raw(sessions, adjust=True, message="deixei mais leve, mantendo a terça"):
    return json.dumps({
        "adjust": adjust,
        "message": message,
        "sessions": sessions,
    })


def test_parse_builds_replace_ops_for_the_adjusted_week():

    raw = _raw([
        {"day": "Tuesday", "workout_type": "Fartlek", "distance_km": 6.0,
         "pace_min": "4:50", "pace_max": "5:00",
         "structure": ["Aquecimento", "6x500m"], "purpose": "velocidade"},
        {"day": "Thursday", "workout_type": "Rodagem leve", "distance_km": 6.0,
         "structure": ["contínuo"], "purpose": "base"},
        {"day": "Saturday", "workout_type": "Longão", "distance_km": 10.0,
         "structure": ["leve"], "purpose": "resistência"},
    ])

    neg = NegotiationEngine._parse(raw, _plan())

    assert neg is not None
    assert neg.message.startswith("deixei mais leve")

    replaces = [o for o in neg.operations if o["action"] == "replace"]
    assert {o["day"] for o in replaces} == {"Tuesday", "Thursday", "Saturday"}
    # a sessão remontada mantém a modalidade do dia e a nova carga
    ter = next(o for o in replaces if o["day"] == "Tuesday")["session"]
    assert ter["kind"] == "run"
    assert ter["planned_distance_km"] == 6.0
    assert ter["workout_type"] == "Fartlek"


def test_parse_drops_a_day_removed_from_the_week():

    # a IA devolveu só ter/qui — sábado saiu -> drop explícito de sábado
    raw = _raw([
        {"day": "Tuesday", "workout_type": "Rodagem", "distance_km": 6.0,
         "structure": ["x"], "purpose": "base"},
        {"day": "Thursday", "workout_type": "Rodagem", "distance_km": 6.0,
         "structure": ["y"], "purpose": "base"},
    ])

    neg = NegotiationEngine._parse(raw, _plan())

    assert neg is not None
    drops = [o for o in neg.operations if o["action"] == "drop"]
    assert [o["day"] for o in drops] == ["Saturday"]


def test_parse_returns_none_when_not_an_adjustment():

    raw = json.dumps({"adjust": False})
    assert NegotiationEngine._parse(raw, _plan()) is None


def test_parse_returns_none_without_message_or_sessions():

    assert NegotiationEngine._parse(_raw([], message=""), _plan()) is None
    assert NegotiationEngine._parse(
        json.dumps({"adjust": True, "message": "oi"}), _plan(),
    ) is None


def test_parse_returns_none_on_garbage():

    assert NegotiationEngine._parse("nao e json", _plan()) is None
