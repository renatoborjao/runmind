import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.coach.planning.move_skip_engine import MoveSkipEngine
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

GEN_TEXT = "app.infrastructure.integrations.gemini.client.generate_text"


def _session(day, kind="run") -> PlannedSession:

    return PlannedSession(
        day=day, workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50", kind=kind,
    )


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=0.0, running_days=[s.day for s in sessions],
        week_start=date(2026, 7, 6), sessions=list(sessions),
    )


def test_parse_skip_valid():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps(
        {"action": "skip", "day": "Tuesday", "message": "tiro o de terça?"}
    )

    request = MoveSkipEngine._parse(raw, plan)

    assert request.action == "skip"
    assert request.day == "Tuesday"
    assert request.target_day is None


def test_parse_move_valid_to_free_day():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps({
        "action": "move", "day": "Tuesday", "target_day": "Wednesday",
        "message": "movo pra quarta?",
    })

    request = MoveSkipEngine._parse(raw, plan)

    assert request.action == "move"
    assert request.day == "Tuesday"
    assert request.target_day == "Wednesday"


def test_parse_move_to_occupied_day_rejected():
    """v1: mover pra dia que já tem treino perderia o do destino -> rejeita."""

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps({
        "action": "move", "day": "Tuesday", "target_day": "Thursday",
        "message": "m",
    })

    assert MoveSkipEngine._parse(raw, plan) is None


def test_parse_day_without_session_rejected():

    plan = _plan(_session("Tuesday"))

    raw = json.dumps({"action": "skip", "day": "Friday", "message": "m"})

    assert MoveSkipEngine._parse(raw, plan) is None


def test_parse_none_action():

    plan = _plan(_session("Tuesday"))

    assert MoveSkipEngine._parse('{"action": "none"}', plan) is None


def test_parse_tolerates_garbage():

    plan = _plan(_session("Tuesday"))

    assert MoveSkipEngine._parse("não é json", plan) is None


def test_propose_calls_ai_and_returns_request():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps({
        "action": "move", "day": "Tuesday", "target_day": "Wednesday",
        "message": "movo o tiro pra quarta? aplico?",
    })

    with patch(GEN_TEXT, new=AsyncMock(return_value=raw)):

        request = asyncio.run(
            MoveSkipEngine.propose(
                make_runner(), plan, "joga o tiro pra quarta",
                date(2026, 7, 6),
            )
        )

    assert request.action == "move"
    assert request.target_day == "Wednesday"
