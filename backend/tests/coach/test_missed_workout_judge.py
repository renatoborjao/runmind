import json
from datetime import date

from app.application.coach.planning.missed_workout_judge import (
    MissedWorkoutJudge,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


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


def test_low_impact_carries_only_a_message():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps({
        "impact": "low",
        "message": "Ontem não rolou, mas o plano segue igual. 💪",
        "operations": [],
    })

    judgment = MissedWorkoutJudge._parse(raw, plan)

    assert judgment.message
    assert judgment.operations == []


def test_meaningful_maps_replace_into_planned_session_shape():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    raw = json.dumps({
        "impact": "meaningful",
        "message": "Dá pra reorganizar seus próximos dias. Aplico?",
        "operations": [{
            "action": "replace",
            "day": "Thursday",
            "session": {
                "workout_type": "Tempo",
                "distance_km": 8.0,
                "pace_min": "5:00", "pace_max": "5:10",
                "purpose": "recolocar limiar",
                "steps": [{"kind": "run", "distance_km": 8}],
            },
        }],
    })

    judgment = MissedWorkoutJudge._parse(raw, plan)

    assert len(judgment.operations) == 1

    op = judgment.operations[0]
    assert op["action"] == "replace"
    assert op["day"] == "Thursday"
    # mapeado pro formato PlannedSession (não os nomes crus da IA)
    assert op["session"]["planned_distance_km"] == 8.0
    assert op["session"]["target_pace_min"] == "5:00"
    assert op["session"]["kind"] == "run"          # herdou do dia original


def test_operations_with_invalid_day_are_discarded():

    plan = _plan(_session("Tuesday"))

    raw = json.dumps({
        "message": "m",
        "operations": [{"action": "drop", "day": "Funday"}],
    })

    judgment = MissedWorkoutJudge._parse(raw, plan)

    assert judgment.operations == []


def test_parse_tolerates_garbage():

    assert MissedWorkoutJudge._parse("não é json", _plan(_session("Tuesday"))) \
        is None
