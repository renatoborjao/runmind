from types import SimpleNamespace
from unittest.mock import patch

from app.application.review.goal_projection_writer import GoalProjectionWriter

MOD = "app.application.review.goal_projection_writer"


def _goal(distance_km=10.0, target_time=None, race_label=None):

    return SimpleNamespace(
        distance_km=distance_km, target_time=target_time,
        race_label=race_label or (f"{distance_km:.0f} km" if distance_km else None),
    )


def _write(goal, pred, weeks=None):

    with patch(f"{MOD}.RaceTimePredictor") as p:

        p.predict_formatted.return_value = pred

        return GoalProjectionWriter.write("Renato", goal, object(), weeks)


def test_no_distance_returns_none():

    assert _write(_goal(distance_km=0), pred=None) is None


def test_no_anchor_prediction_returns_none():

    assert _write(_goal(), pred=None) is None


def test_projection_without_target_shows_estimate_only():

    msg = _write(
        _goal(target_time=None),
        pred={"formatted": "52:00", "delta_seconds": None,
              "delta_formatted": None},
    )

    assert "52:00" in msg
    assert "Rumo à sua meta" in msg
    assert "faltam" not in msg.lower()  # sem alvo, sem gap


def test_gap_when_behind_target():

    msg = _write(
        _goal(target_time="45:00"),
        pred={"formatted": "50:00", "delta_seconds": 300,
              "delta_formatted": "5:00"},
    )

    assert "faltam" in msg.lower()
    assert "5:00" in msg
    assert "30 s/km" in msg  # 300s / 10km = 30 s/km


def test_already_on_target():

    msg = _write(
        _goal(target_time="50:00"),
        pred={"formatted": "49:30", "delta_seconds": -30,
              "delta_formatted": "0:30"},
    )

    assert "JÁ está no ritmo" in msg


def test_weeks_to_race_line():

    msg = _write(
        _goal(target_time=None),
        pred={"formatted": "52:00", "delta_seconds": None,
              "delta_formatted": None},
        weeks=3,
    )

    assert "3 semanas" in msg
