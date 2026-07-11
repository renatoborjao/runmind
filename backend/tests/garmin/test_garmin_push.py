from datetime import date
from unittest.mock import MagicMock, patch

from app.application.garmin.garmin_push import push_session, remove_session
from app.domain.entities.planned_session import PlannedSession

MODULE = "app.application.garmin.garmin_push"


def _session() -> PlannedSession:

    return PlannedSession(
        day="Tuesday",
        workout_type="Rodagem",
        objective="",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min="5:40",
        target_pace_max="5:55",
    )


def test_push_session_captures_workout_and_schedule_ids():

    garmin = MagicMock()
    garmin.upload_running_workout.return_value = {"workoutId": 111}
    # chave confirmada no device real (renato2)
    garmin.schedule_workout.return_value = {"workoutScheduleId": 999}

    with patch(f"{MODULE}.GarminClient") as gc:

        gc.connect.return_value = garmin

        out = push_session("renato2", _session(), date(2026, 7, 7))

    assert out["ok"] is True
    assert out["workout_id"] == 111
    assert out["schedule_id"] == 999
    garmin.schedule_workout.assert_called_once_with(111, "2026-07-07")


def test_remove_session_deletes_template_which_cascades():

    # confirmado no device: apagar o template já tira do calendário —
    # remove_session NÃO precisa desagendar
    garmin = MagicMock()

    with patch(f"{MODULE}.GarminClient") as gc:

        gc.connect.return_value = garmin

        out = remove_session(
            "renato2", {"workout_id": 111, "schedule_id": 999},
        )

    garmin.delete_workout.assert_called_once_with(111)
    garmin.unschedule_workout.assert_not_called()
    assert out["ok"] is True
    assert out["workout_id"] == 111
