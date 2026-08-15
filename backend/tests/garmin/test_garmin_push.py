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


def test_sweep_removes_our_orphans_keeps_plan_and_athlete_workouts():
    """Varredura: apaga só treinos NOSSOS fora do plano atual. Preserva os do
    plano (keep_ids), os avulsos (estão no plano) e o que o ATLETA criou."""

    from app.application.garmin.garmin_push import sweep_orphan_workouts

    garmin = MagicMock()
    garmin.get_workouts.return_value = [
        {"workoutId": 1, "workoutName": "Ritmind · Tempo Run 7.5km"},   # plano
        {"workoutId": 2, "workoutName": "Ritmind · Longão 14.0km"},     # plano
        {"workoutId": 3, "workoutName": "Ritmind · Fartlek 8.0km"},     # órfão nosso
        {"workoutId": 4, "workoutName": "RunMind · Longão 13.5km"},     # órfão (rebrand)
        {"workoutId": 5, "workoutName": "Meu treino pessoal"},          # do atleta
    ]

    removed = sweep_orphan_workouts("renato2", keep_ids={1, 2}, garmin=garmin)

    assert removed == [3, 4]                       # só os órfãos nossos
    deleted = [c.args[0] for c in garmin.delete_workout.call_args_list]
    assert deleted == [3, 4]
    assert 1 not in deleted and 2 not in deleted   # plano preservado
    assert 5 not in deleted                         # treino do atleta preservado


def test_sweep_preserves_protected_workouts():
    """Treino de prova/avulso PROTEGIDO (fora do plano) não é varrido."""

    from app.application.garmin.garmin_push import sweep_orphan_workouts

    garmin = MagicMock()
    garmin.get_workouts.return_value = [
        {"workoutId": 1, "workoutName": "Ritmind · Tempo Run 7.5km"},  # plano
        {"workoutId": 7, "workoutName": "Ritmind · Prova 10.0km"},     # protegido
        {"workoutId": 9, "workoutName": "Ritmind · Fartlek 8.0km"},    # órfão
    ]

    with patch(
        "app.infrastructure.persistence.protected_workout_store."
        "ProtectedWorkoutStore"
    ) as store:

        store.return_value.ids.return_value = {7}

        removed = sweep_orphan_workouts("renato2", keep_ids={1}, garmin=garmin)

    assert removed == [9]           # só o órfão
    assert 7 not in removed         # prova protegida sobrevive


def test_sweep_best_effort_never_raises():

    from app.application.garmin.garmin_push import sweep_orphan_workouts

    garmin = MagicMock()
    garmin.get_workouts.side_effect = Exception("garmin fora do ar")

    # não levanta — best-effort
    assert sweep_orphan_workouts("renato2", keep_ids=set(), garmin=garmin) == []
