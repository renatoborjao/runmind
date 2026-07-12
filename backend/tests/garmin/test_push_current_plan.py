import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.garmin.push_current_plan import push_current_plan
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.garmin.push_current_plan"


def _plan(days) -> TrainingPlan:
    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="BUILD",
        weekly_volume=20.0, running_days=days,
        week_start=date(2026, 7, 13),
        sessions=[
            PlannedSession(
                day=d, workout_type="Rodagem", objective="",
                planned_distance_km=8.0, planned_duration_minutes=None,
                target_pace_min="6:00", target_pace_max="6:30", kind="run",
            )
            for d in days
        ],
    )


def _run(snapshot):

    current = _plan(["Tuesday", "Thursday", "Saturday"])

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.GarminReconciler") as reconciler,
        patch(f"{MODULE}.WeeklyPlanRepository") as repo,
        patch(f"{MODULE}.PushedPlanStore") as store,
    ):

        provider.for_profile = AsyncMock(
            return_value=(make_runner(), current),
        )
        garmin.connect.return_value = MagicMock()
        reconciler.reconcile.return_value = []
        store.load.return_value = snapshot

        asyncio.run(push_current_plan("renato2"))

        return current, reconciler, store


def test_reconciles_against_the_pushed_snapshot_not_itself():
    """Regenerou o plano (Dom virou Sáb): reconcilia contra o que JÁ está no
    relógio (snapshot Ter/Qui/Dom), pra remover o Dom antigo e empurrar o Sáb
    novo — não contra o próprio plano atual."""

    snapshot = _plan(["Tuesday", "Thursday", "Sunday"])

    current, reconciler, store = _run(snapshot)

    call = reconciler.reconcile.call_args
    assert call.kwargs["previous_plan"] is snapshot     # o do relógio
    assert call.kwargs["current_plan"] is current       # o novo
    # snapshot atualizado pro estado novo (base da próxima reconciliação)
    store.save.assert_called_once_with("renato2", current)


def test_first_push_without_snapshot_reconciles_against_itself():
    """Primeira vez (sem snapshot): previous = o próprio plano -> empurra tudo,
    idempotente (comportamento original preservado)."""

    current, reconciler, _ = _run(snapshot=None)

    call = reconciler.reconcile.call_args
    assert call.kwargs["previous_plan"] is current
    assert call.kwargs["current_plan"] is current
