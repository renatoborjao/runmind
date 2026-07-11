import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.coach.planning.aversion_swap_engine import (
    AversionSwapEngine,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.planning.aversion_swap_engine"


def _session(day, kind="run") -> PlannedSession:

    return PlannedSession(
        day=day, workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50", kind=kind,
    )


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k sub-50", phase="IA",
        weekly_volume=0.0, running_days=[s.day for s in sessions],
        week_start=date(2026, 7, 6), sessions=list(sessions),
    )


def _swap_json(day="Tuesday") -> str:

    return json.dumps({
        "found": True,
        "day": day,
        "reason": "chatice",
        "session": {
            "workout_type": "Fartlek",
            "distance_km": 9.0,
            "pace_min": "4:45", "pace_max": "5:30",
            "purpose": "manter velocidade sem a pista",
            "structure": ["Aquecimento 2 km", "8x (1min forte/1min trote)"],
            "steps": [
                {"kind": "warmup", "distance_km": 2},
                {"kind": "repeat", "reps": 8, "steps": [
                    {"kind": "interval", "duration_min": 1, "pace_min": "4:45"},
                    {"kind": "recovery", "duration_min": 1},
                ]},
            ],
        },
        "message": "Vi que você não curte tiro na pista. Troco por um "
                   "fartlek na rua, mantém a velocidade. Aplico?",
    })


def test_parse_builds_swap_inheriting_kind_from_original():

    plan = _plan(_session("Tuesday", kind="run"))

    swap = AversionSwapEngine._parse(_swap_json("Tuesday"), plan)

    assert swap is not None
    assert swap.day == "Tuesday"
    assert swap.session["workout_type"] == "Fartlek"
    assert swap.session["kind"] == "run"           # herdou do treino original
    assert swap.session["planned_distance_km"] == 9.0
    assert swap.session["steps"]                    # cru, o applier reidrata
    assert "Aplico?" in swap.message


def test_parse_returns_none_when_not_an_aversion():

    plan = _plan(_session("Tuesday"))

    assert AversionSwapEngine._parse('{"found": false}', plan) is None


def test_parse_rejects_day_absent_from_plan():

    plan = _plan(_session("Tuesday"))

    assert AversionSwapEngine._parse(_swap_json("Friday"), plan) is None


def test_parse_tolerates_garbage():

    plan = _plan(_session("Tuesday"))

    assert AversionSwapEngine._parse("isto não é json", plan) is None


def test_propose_calls_the_ai_and_returns_a_swap():

    plan = _plan(_session("Tuesday", kind="run"))

    with patch(
        f"{MODULE}.generate_text",
        new=AsyncMock(return_value=_swap_json("Tuesday")),
    ):

        swap = asyncio.run(
            AversionSwapEngine.propose(
                make_runner(), plan, "não curto tiro na pista",
            )
        )

    assert swap.day == "Tuesday"
    assert swap.session["workout_type"] == "Fartlek"
