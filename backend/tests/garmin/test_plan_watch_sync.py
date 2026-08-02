import asyncio
from unittest.mock import MagicMock, patch

from app.application.garmin.plan_watch_sync import resync_watch_if_pushed

MODULE = "app.application.garmin.plan_watch_sync"


def _run(*, connected, snapshot, reconcile_raises=False):

    plan = MagicMock(name="plan_regenerado")

    with (
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.PushedPlanStore") as store,
        patch(f"{MODULE}.GarminReconciler") as reconciler,
        patch(f"{MODULE}.WeeklyPlanRepository") as weekly,
    ):

        garmin.is_connected.return_value = connected
        garmin.connect.return_value = MagicMock(name="garmin_conn")
        store.load.return_value = snapshot

        if reconcile_raises:
            reconciler.reconcile.side_effect = RuntimeError("relógio fora")

        synced = asyncio.run(resync_watch_if_pushed("renato", plan))

        return synced, reconciler, weekly, store, plan


def test_syncs_when_connected_and_previously_pushed():

    previous = MagicMock(name="snapshot")

    synced, reconciler, weekly, store, plan = _run(
        connected=True, snapshot=previous,
    )

    assert synced is True
    # reconcilia o plano REGERADO contra o snapshot do que estava no relógio
    reconciler.reconcile.assert_called_once()
    kwargs = reconciler.reconcile.call_args.kwargs
    assert kwargs["previous_plan"] is previous
    assert kwargs["current_plan"] is plan
    # persiste os registros de push + novo snapshot
    weekly.return_value.save.assert_called_once_with("renato", plan)
    store.save.assert_called_once_with("renato", plan)


def test_skips_when_not_connected():

    synced, reconciler, weekly, store, _ = _run(
        connected=False, snapshot=MagicMock(),
    )

    assert synced is False
    reconciler.reconcile.assert_not_called()
    weekly.return_value.save.assert_not_called()
    store.save.assert_not_called()


def test_skips_when_never_pushed():
    """Sem snapshot = nunca sincronizou: NÃO surpreende o atleta empurrando
    treinos do nada — o push segue opt-in."""

    synced, reconciler, weekly, store, _ = _run(
        connected=True, snapshot=None,
    )

    assert synced is False
    reconciler.reconcile.assert_not_called()
    store.save.assert_not_called()


def test_reconcile_failure_is_swallowed():
    """Falha no relógio nunca derruba a resposta ao atleta — devolve False e
    o plano no app segue como fonte de verdade (reconcilia depois)."""

    synced, reconciler, weekly, store, _ = _run(
        connected=True, snapshot=MagicMock(), reconcile_raises=True,
    )

    assert synced is False
    # tentou, falhou, não persistiu snapshot novo
    store.save.assert_not_called()
