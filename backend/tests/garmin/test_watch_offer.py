from unittest.mock import MagicMock, patch

from app.application.garmin.watch_offer import watch_update_offer

MODULE = "app.application.garmin.watch_offer"


def _run(*, connected, snapshot):

    with (
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.PushedPlanStore") as store,
        patch(f"{MODULE}.GarminOfferStore") as offer,
    ):

        garmin.is_connected.return_value = connected
        store.load.return_value = snapshot

        line = watch_update_offer("renato")

        return line, offer


def test_offers_and_arms_pending_when_connected_and_previously_pushed():

    line, offer = _run(connected=True, snapshot=MagicMock())

    assert "relógio" in line
    assert "sim" in line.lower()
    # armou o pending pra o 'sim' seguinte empurrar (via GarminSync)
    offer.set_pending.assert_called_once_with("renato")


def test_silent_when_not_connected():

    line, offer = _run(connected=False, snapshot=MagicMock())

    assert line == ""
    offer.set_pending.assert_not_called()


def test_silent_when_never_pushed():
    """Nunca sincronizou: não oferece no meio de uma mudança pontual (sem
    ruído) — ele opta no domingo."""

    line, offer = _run(connected=True, snapshot=None)

    assert line == ""
    offer.set_pending.assert_not_called()
