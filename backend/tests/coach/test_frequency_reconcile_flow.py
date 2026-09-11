import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.coach.conversation.frequency_reconcile_flow import (
    FrequencyReconcileFlow,
)

MOD = "app.application.coach.conversation.frequency_reconcile_flow"


def _runner(external=False):

    return SimpleNamespace(
        name="Hélio", external_coach=external,
        preferred_running_days=["Monday", "Wednesday", "Saturday"],
    )


def _run(pending, text, external=False):

    repo = MagicMock()

    with (
        patch(f"{MOD}.FrequencyOfferStore") as store,
        patch(f"{MOD}.RunnerProfileRepository", return_value=repo),
    ):
        store.get_pending.return_value = pending

        msg = asyncio.run(
            FrequencyReconcileFlow.resolve_reply("helio", _runner(external), text)
        )

    return msg, repo, store


def test_no_pending_returns_none():

    msg, _, _ = _run(None, "sim")

    assert msg is None


def test_unclear_keeps_offer_and_returns_none():

    msg, _, store = _run({"days": 4, "weekday": "Friday"}, "e o meu longão?")

    assert msg is None
    store.clear.assert_not_called()


def test_confirm_officializes_day_but_defers_to_next_week():

    msg, repo, store = _run({"days": 4, "weekday": "Friday"}, "sim, pode!")

    # perfil atualizado com o 4º dia (sexta), na ordem Seg..Dom
    args = repo.update_fields.call_args.args[1]
    assert args["preferred_running_days"] == [
        "Monday", "Wednesday", "Friday", "Saturday"
    ]
    assert args["weekly_training_days"] == 4
    # NÃO remexe a semana atual: defere pro domingo, sem oferta de relógio
    assert "sexta" in msg
    assert "domingo" in msg.lower()
    assert "semana atual" in msg.lower()
    store.clear.assert_called_once()


def test_confirm_does_not_regenerate_current_week():

    msg, repo, _ = _run({"days": 4, "weekday": "Friday"}, "sim, pode!")

    # nada de plano regenerado nem oferta de relógio nesta semana
    assert "<PLANO>" not in msg
    assert "oferta" not in msg


def test_reject_keeps_days():

    msg, repo, store = _run({"days": 4, "weekday": "Friday"}, "não, deixa 3")

    repo.update_fields.assert_not_called()
    assert "Mantenho" in msg
    store.clear.assert_called_once()


def test_external_coach_updates_without_regenerating():

    msg, repo, _ = _run({"days": 4, "weekday": "Friday"}, "isso", external=True)

    repo.update_fields.assert_called_once()
    assert "<PLANO>" not in msg
