from datetime import date
from unittest.mock import MagicMock, patch

from app.application.garmin.garmin_reconciler import (
    GarminReconciler,
    session_fingerprint,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

MODULE = "app.application.garmin.garmin_reconciler"

WEEK_START = date(2026, 7, 6)      # segunda
TUESDAY = date(2026, 7, 7)

PROFILE = "renato"


def _session(day, **overrides) -> PlannedSession:

    defaults = dict(
        day=day,
        workout_type="Rodagem",
        objective="",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min="5:40",
        target_pace_max="5:55",
    )

    defaults.update(overrides)

    return PlannedSession(**defaults)


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="IA",
        weekly_volume=0.0,
        running_days=[s.day for s in sessions],
        week_start=WEEK_START,
        sessions=list(sessions),
    )


def _patched(push_ok=True):
    """push_session devolve ids incrementais; remove_session é espião."""

    counter = {"n": 0}

    def _push(profile, session, on_date, garmin=None):

        counter["n"] += 1

        if not push_ok:

            return {"ok": False, "error": "garmin caiu"}

        return {
            "ok": True,
            "workout_id": counter["n"],
            "schedule_id": 100 + counter["n"],
            "date": on_date.isoformat(),
        }

    push = MagicMock(side_effect=_push)
    remove = MagicMock(return_value={"ok": True})

    return push, remove


def _run(previous, current, push_ok=True, reference=TUESDAY):

    push, remove = _patched(push_ok)

    with (
        patch(f"{MODULE}.push_session", push),
        patch(f"{MODULE}.remove_session", remove),
    ):

        results = GarminReconciler.reconcile(
            PROFILE, previous, current, reference_date=reference,
        )

    return results, push, remove


def test_first_push_sends_each_running_session_and_records_it():

    plan = _plan(
        _session("Tuesday"),
        _session("Thursday", workout_type="Velocidade"),
    )

    results, push, remove = _run(previous=plan, current=plan)

    # ambas empurradas, nenhuma removida
    assert push.call_count == 2
    remove.assert_not_called()
    assert all(r["action"] == "pushed" and r["ok"] for r in results)

    # registro gravado na sessão (com fingerprint pra reconciliar depois)
    tue = plan.find_session_by_day("Tuesday")
    assert tue.garmin["workout_id"] == 1
    assert tue.garmin["schedule_id"] == 101
    assert tue.garmin["date"] == TUESDAY.isoformat()
    assert tue.garmin["fingerprint"]


def test_non_running_sessions_are_ignored():

    plan = _plan(
        _session("Tuesday"),
        _session("Monday", kind="strength"),
    )

    results, push, remove = _run(previous=plan, current=plan)

    assert push.call_count == 1
    assert {r["day"] for r in results} == {"Tuesday"}


def test_repush_of_unchanged_plan_is_idempotent():

    plan = _plan(_session("Tuesday"), _session("Thursday"))

    # 1ª reconciliação grava os registros
    _run(previous=plan, current=plan)

    # 2ª: mesmo plano, já com registros -> nada é empurrado nem removido
    results, push, remove = _run(previous=plan, current=plan)

    push.assert_not_called()
    remove.assert_not_called()
    assert all(r["action"] == "kept" for r in results)


def test_changed_content_replaces_on_the_watch():

    old = _plan(_session("Tuesday", planned_distance_km=8.0))

    _run(previous=old, current=old)   # grava registro

    old_record = old.find_session_by_day("Tuesday").garmin

    # novo plano: mesma terça, distância diferente -> conteúdo mudou
    new = _plan(_session("Tuesday", planned_distance_km=12.0))

    results, push, remove = _run(previous=old, current=new)

    # tira o antigo do relógio e empurra o novo (cliente reusado = None no teste)
    remove.assert_called_once_with(PROFILE, old_record, None)
    push.assert_called_once()
    assert results[0]["action"] == "replaced"
    assert new.find_session_by_day("Tuesday").garmin["fingerprint"] != \
        old_record["fingerprint"]


def test_dropped_session_is_removed_from_the_watch():

    old = _plan(_session("Tuesday"), _session("Thursday"))

    _run(previous=old, current=old)   # grava registros

    dropped_record = old.find_session_by_day("Thursday").garmin

    # quinta caiu do plano (drop): só terça permanece
    new = _plan(_session("Tuesday"))
    new.find_session_by_day("Tuesday").garmin = (
        old.find_session_by_day("Tuesday").garmin
    )

    results, push, remove = _run(previous=old, current=new)

    push.assert_not_called()                       # terça não mudou
    remove.assert_called_once_with(PROFILE, dropped_record, None)
    assert any(r["action"] == "removed" and r["day"] == "Thursday"
               for r in results)


def test_moved_session_pushes_new_day_and_removes_old():

    old = _plan(_session("Tuesday"))

    _run(previous=old, current=old)

    old_record = old.find_session_by_day("Tuesday").garmin

    # mesmo treino, agora na quarta
    new = _plan(_session("Wednesday"))

    results, push, remove = _run(previous=old, current=new)

    push.assert_called_once()                       # empurra quarta
    remove.assert_called_once_with(PROFILE, old_record, None)  # tira terça
    actions = {r["day"]: r["action"] for r in results}
    assert actions["Wednesday"] == "pushed"
    assert actions["Thursday" if False else "Tuesday"] == "removed"


def test_past_sessions_are_left_untouched():

    # terça é a referência; segunda já passou
    plan = _plan(_session("Monday"), _session("Tuesday"))

    results, push, remove = _run(
        previous=plan, current=plan, reference=TUESDAY,
    )

    push.assert_called_once()                       # só terça
    assert {r["day"] for r in results} == {"Tuesday"}
    assert plan.find_session_by_day("Monday").garmin is None


def test_failed_push_leaves_no_record():

    plan = _plan(_session("Tuesday"))

    results, push, remove = _run(previous=plan, current=plan, push_ok=False)

    assert results[0]["action"] == "failed"
    assert results[0]["ok"] is False
    assert plan.find_session_by_day("Tuesday").garmin is None


def test_fingerprint_changes_with_content_and_is_stable():

    a = _session("Tuesday", planned_distance_km=8.0)
    b = _session("Tuesday", planned_distance_km=8.0)
    c = _session("Tuesday", planned_distance_km=12.0)

    assert session_fingerprint(a) == session_fingerprint(b)
    assert session_fingerprint(a) != session_fingerprint(c)
