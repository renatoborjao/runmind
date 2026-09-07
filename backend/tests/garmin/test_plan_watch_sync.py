import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.garmin.plan_watch_sync import resync_watch_if_pushed

MODULE = "app.application.garmin.plan_watch_sync"
PUSH = "app.application.garmin.push_current_plan.push_current_plan"


def _run(*, connected, snapshot, push_raises=False):

    plan = MagicMock(name="plan_regenerado")

    with (
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.PushedPlanStore") as store,
        patch(PUSH, new_callable=AsyncMock) as push,
    ):

        garmin.is_connected.return_value = connected
        store.load.return_value = snapshot

        if push_raises:
            push.side_effect = RuntimeError("relógio fora")

        synced = asyncio.run(resync_watch_if_pushed("renato", plan))

        return synced, push, store, plan


def test_full_refresh_when_connected_and_previously_pushed():
    """Entrega de domingo re-empurra a semana INTEIRA com full_refresh -> tudo
    cai em 'Programado' (não split entre 'Meus treinos' e 'Programado')."""

    synced, push, store, _ = _run(connected=True, snapshot=MagicMock())

    assert synced is True
    push.assert_awaited_once_with("renato", full_refresh=True)


def test_skips_when_not_connected():

    synced, push, store, _ = _run(connected=False, snapshot=MagicMock())

    assert synced is False
    push.assert_not_awaited()


def test_skips_when_never_pushed():
    """Sem snapshot = nunca sincronizou: NÃO surpreende o atleta empurrando
    treinos do nada — o push segue opt-in."""

    synced, push, store, _ = _run(connected=True, snapshot=None)

    assert synced is False
    push.assert_not_awaited()


def test_push_failure_is_swallowed():
    """Falha no relógio nunca derruba a resposta ao atleta — devolve False."""

    synced, push, store, _ = _run(
        connected=True, snapshot=MagicMock(), push_raises=True,
    )

    assert synced is False
