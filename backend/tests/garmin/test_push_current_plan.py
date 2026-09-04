import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.garmin.push_current_plan import push_current_plan
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.garmin.push_current_plan"

# âncora dentro da semana do plano, pra as sessões contarem como FUTURAS
MONDAY = date(2026, 7, 13)


def _plan(days, records=None) -> TrainingPlan:
    records = records or {}
    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="BUILD",
        weekly_volume=20.0, running_days=days,
        week_start=MONDAY,
        sessions=[
            PlannedSession(
                day=d, workout_type="Rodagem", objective="",
                planned_distance_km=8.0, planned_duration_minutes=None,
                target_pace_min="6:00", target_pace_max="6:30", kind="run",
                garmin=records.get(d),
            )
            for d in days
        ],
    )


def _run(snapshot, full_refresh=True, current=None):

    current = current or _plan(["Tuesday", "Thursday", "Saturday"])

    g = MagicMock()

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.GarminReconciler") as reconciler,
        patch(f"{MODULE}.WeeklyPlanRepository"),
        patch(f"{MODULE}.PushedPlanStore") as store,
        patch(f"{MODULE}.sweep_orphan_workouts"),
        patch(f"{MODULE}.today_local", return_value=MONDAY),
    ):

        provider.for_profile = AsyncMock(
            return_value=(make_runner(), current),
        )
        garmin.connect.return_value = g
        reconciler.reconcile.return_value = []
        store.load.return_value = snapshot

        asyncio.run(push_current_plan("renato2", full_refresh=full_refresh))

        return current, reconciler, store, g


def test_full_refresh_default_repushes_the_whole_week_fresh():
    """Padrão (full_refresh): apaga os templates FUTUROS já no relógio, zera os
    registros e reconcilia contra o plano FRESCO — replica o disparo de domingo
    pra o relógio repovoar 'Programado'. Ver [[project_rede_relogio]]."""

    current = _plan(
        ["Tuesday", "Thursday", "Saturday"],
        records={
            "Tuesday": {"workout_id": 11, "schedule_id": 111,
                        "date": "2026-07-14", "fingerprint": "a"},
            "Thursday": {"workout_id": 22, "schedule_id": 222,
                         "date": "2026-07-16", "fingerprint": "b"},
            "Saturday": {"workout_id": 33, "schedule_id": 333,
                         "date": "2026-07-18", "fingerprint": "c"},
        },
    )

    snapshot = _plan(["Tuesday", "Thursday", "Sunday"])

    current, reconciler, store, g = _run(snapshot, current=current)

    # apagou os 3 templates futuros que estavam no relógio
    deleted = {c.args[0] for c in g.delete_workout.call_args_list}
    assert deleted == {11, 22, 33}

    # registros zerados -> reconciliador re-empurra tudo do zero
    assert all(s.garmin is None for s in current.sessions)

    # reconcilia contra o plano FRESCO (não o snapshot): tudo vira push novo
    call = reconciler.reconcile.call_args
    assert call.kwargs["previous_plan"] is current
    assert call.kwargs["current_plan"] is current
    store.save.assert_called_once_with("renato2", current)


def test_full_refresh_leaves_past_sessions_untouched():
    """A purga só mexe no FUTURO: sessão que já passou mantém o registro."""

    current = _plan(
        ["Tuesday", "Thursday", "Saturday"],
        records={
            "Tuesday": {"workout_id": 11, "schedule_id": 111,
                        "date": "2026-07-14", "fingerprint": "a"},
        },
    )
    # today = Thursday 2026-07-16 -> terça (14) já passou
    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.GarminReconciler") as reconciler,
        patch(f"{MODULE}.WeeklyPlanRepository"),
        patch(f"{MODULE}.PushedPlanStore") as store,
        patch(f"{MODULE}.sweep_orphan_workouts"),
        patch(f"{MODULE}.today_local", return_value=date(2026, 7, 16)),
    ):
        g = MagicMock()
        provider.for_profile = AsyncMock(return_value=(make_runner(), current))
        garmin.connect.return_value = g
        reconciler.reconcile.return_value = []
        store.load.return_value = None

        asyncio.run(push_current_plan("renato2"))

    # terça já passou: NÃO foi apagada, registro preservado
    g.delete_workout.assert_not_called()
    assert current.find_session_by_day("Tuesday").garmin is not None


def test_incremental_reconciles_against_the_pushed_snapshot():
    """full_refresh=False mantém o caminho incremental: reconcilia contra o que
    JÁ está no relógio (snapshot), sem purgar."""

    snapshot = _plan(["Tuesday", "Thursday", "Sunday"])

    current, reconciler, store, g = _run(snapshot, full_refresh=False)

    g.delete_workout.assert_not_called()                 # não purga
    call = reconciler.reconcile.call_args
    assert call.kwargs["previous_plan"] is snapshot      # o do relógio
    assert call.kwargs["current_plan"] is current
    store.save.assert_called_once_with("renato2", current)


def test_incremental_first_push_without_snapshot_reconciles_against_itself():
    """full_refresh=False, primeira vez (sem snapshot): previous = o próprio
    plano -> empurra tudo, idempotente."""

    current, reconciler, _, _ = _run(snapshot=None, full_refresh=False)

    call = reconciler.reconcile.call_args
    assert call.kwargs["previous_plan"] is current
    assert call.kwargs["current_plan"] is current
