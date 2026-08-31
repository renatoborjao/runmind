import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    plan = SimpleNamespace(sessions=[])

    with (
        patch(f"{MOD}.FrequencyOfferStore") as store,
        patch(f"{MOD}.RunnerProfileRepository", return_value=repo),
        patch(f"{MOD}.CurrentPlanProvider.for_profile",
              new=AsyncMock(return_value=(_runner(), plan))),
        patch(f"{MOD}.WeeklyPlanMessageFormatter.week_plan_message",
              return_value="<PLANO>"),
        patch(f"{MOD}.watch_update_offer", return_value="\n\n⌚ oferta"),
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


def test_confirm_officializes_day_and_regenerates():

    msg, repo, store = _run({"days": 4, "weekday": "Friday"}, "sim, pode!")

    # perfil atualizado com o 4º dia (sexta), na ordem Seg..Dom
    args = repo.update_fields.call_args.args[1]
    assert args["preferred_running_days"] == [
        "Monday", "Wednesday", "Friday", "Saturday"
    ]
    assert args["weekly_training_days"] == 4
    assert "sexta" in msg and "<PLANO>" in msg and "oferta" in msg
    store.clear.assert_called_once()


def test_reject_keeps_days():

    msg, repo, store = _run({"days": 4, "weekday": "Friday"}, "não, deixa 3")

    repo.update_fields.assert_not_called()
    assert "Mantenho" in msg
    store.clear.assert_called_once()


def test_external_coach_updates_without_regenerating():

    msg, repo, _ = _run({"days": 4, "weekday": "Friday"}, "isso", external=True)

    repo.update_fields.assert_called_once()
    assert "<PLANO>" not in msg
