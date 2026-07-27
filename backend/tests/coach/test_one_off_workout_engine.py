import json

from app.application.coach.planning.one_off_workout_engine import (
    OneOffWorkoutEngine,
)


def _raw(session=None, message="Montei uma rodagem leve pra domingo 💪"):
    payload = {"message": message}
    if session is not None:
        payload["session"] = session
    return json.dumps(payload)


def test_parse_builds_oneoff_session():

    raw = _raw(
        {
            "workout_type": "Rodagem leve",
            "distance_km": 8.0,
            "pace_min": "6:00",
            "pace_max": "6:30",
            "structure": ["Aquecimento", "8 km confortáveis"],
            "steps": [
                {"kind": "run", "distance_km": 8,
                 "pace_min": "6:00", "pace_max": "6:30"}
            ],
            "purpose": "base aeróbica complementando a semana",
        }
    )

    result = OneOffWorkoutEngine._parse(raw, "Sunday")

    assert result is not None
    assert result.message.startswith("Montei")
    assert result.session["day"] == "Sunday"
    assert result.session["kind"] == "run"
    assert result.session["planned_distance_km"] == 8.0
    # marcada como treino nosso avulso
    assert result.session["origin"] == "oneoff"


def test_parse_none_without_session():

    assert OneOffWorkoutEngine._parse(_raw(session=None), "Sunday") is None


def test_parse_none_without_message():

    raw = json.dumps({"session": {"workout_type": "Rodagem", "distance_km": 6}})

    assert OneOffWorkoutEngine._parse(raw, "Sunday") is None


def test_parse_none_on_session_without_workout_type():
    """build_session_dict devolve None sem workout_type -> engine devolve None."""

    raw = _raw({"distance_km": 8.0, "pace_min": "6:00"})

    assert OneOffWorkoutEngine._parse(raw, "Sunday") is None


def test_parse_none_on_garbage():

    assert OneOffWorkoutEngine._parse("isso não é json", "Sunday") is None
