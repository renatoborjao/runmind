import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.garmin.watch_update_reminder_notifier import (
    WatchUpdateReminderNotifier,
)
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_planned_session, make_runner

MOD = "app.application.garmin.watch_update_reminder_notifier"

# semana começa segunda 24/08; "hoje" é quinta 27/08 -> sábado 29/08 é futuro
WEEK_START = date(2026, 8, 24)
TODAY = date(2026, 8, 27)


def _plan(sat_min, sat_max):

    return TrainingPlan(
        athlete_name="Mauricio",
        objective="meia maratona",
        phase="BUILD",
        weekly_volume=24.0,
        running_days=["Tuesday", "Saturday"],
        week_start=WEEK_START,
        sessions=[
            make_planned_session(day="Tuesday", workout_type="Fartlek"),
            make_planned_session(
                day="Saturday",
                workout_type="Longão",
                planned_distance_km=9.0,
                target_pace_min=sat_min,
                target_pace_max=sat_max,
            ),
        ],
    )


def _run(
    *,
    due=True,
    connected=True,
    external=False,
    hour=10,
    current,
    pushed,
):

    runner = make_runner(name="Mauricio", external_coach=external)

    with (
        patch(f"{MOD}.RunnerProfileRepository") as repo_cls,
        patch(f"{MOD}.LoadRunnerProfile") as load_runner,
        patch(f"{MOD}.GarminOfferStore") as offer,
        patch(f"{MOD}.GarminClient") as garmin,
        patch(f"{MOD}.WeeklyPlanRepository") as plan_cls,
        patch(f"{MOD}.PushedPlanStore") as pushed_store,
        patch(f"{MOD}.CoachOutbox") as outbox,
        patch(f"{MOD}.now_in", return_value=SimpleNamespace(hour=hour)),
        patch(f"{MOD}.today_local", return_value=TODAY),
        patch(f"{MOD}.use_athlete_timezone"),
    ):

        repo_cls.return_value.list_all.return_value = ["mauricio"]
        load_runner.execute.return_value = runner
        offer.reminder_due.return_value = due
        garmin.is_connected.return_value = connected
        plan_cls.return_value.load.return_value = current
        pushed_store.load.return_value = pushed
        outbox.send = AsyncMock()

        asyncio.run(WatchUpdateReminderNotifier.notify_all())

        return outbox, offer


def test_reminds_when_watch_is_stale_and_offer_unanswered():

    outbox, offer = _run(
        current=_plan("6:20", "6:50"),  # plano atualizado
        pushed=_plan("6:45", "7:05"),   # relógio na versão antiga
    )

    outbox.send.assert_awaited_once()
    _, msg = outbox.send.await_args.args
    assert "relógio" in msg
    assert "sábado" in msg.lower()
    assert "sim" in msg.lower()
    # um lembrete por episódio; oferta segue viva pro "sim"
    offer.mark_reminded.assert_called_once_with("mauricio")
    offer.clear.assert_not_called()


def test_silent_when_offer_not_due():

    outbox, offer = _run(
        due=False,
        current=_plan("6:20", "6:50"),
        pushed=_plan("6:45", "7:05"),
    )

    outbox.send.assert_not_awaited()
    offer.mark_reminded.assert_not_called()


def test_clears_and_silent_when_watch_already_in_sync():
    """Plano igual ao que está no relógio: a falha se resolveu por outro
    caminho -> encerra a oferta sem incomodar."""

    outbox, offer = _run(
        current=_plan("6:20", "6:50"),
        pushed=_plan("6:20", "6:50"),
    )

    outbox.send.assert_not_awaited()
    offer.clear.assert_called_once_with("mauricio")
    offer.mark_reminded.assert_not_called()


def test_clears_and_silent_for_external_coach():

    outbox, offer = _run(
        external=True,
        current=_plan("6:20", "6:50"),
        pushed=_plan("6:45", "7:05"),
    )

    outbox.send.assert_not_awaited()
    offer.clear.assert_called_once_with("mauricio")


def test_clears_and_silent_when_disconnected():

    outbox, offer = _run(
        connected=False,
        current=_plan("6:20", "6:50"),
        pushed=_plan("6:45", "7:05"),
    )

    outbox.send.assert_not_awaited()
    offer.clear.assert_called_once_with("mauricio")


def test_silent_outside_local_hour():

    outbox, offer = _run(
        hour=3,
        current=_plan("6:20", "6:50"),
        pushed=_plan("6:45", "7:05"),
    )

    outbox.send.assert_not_awaited()
    offer.mark_reminded.assert_not_called()


def test_no_reminder_when_only_past_day_differs():
    """Se o único treino diferente já passou, não adianta cobrar o relógio."""

    # muda a TERÇA (25/08, já passou em relação a 27/08); sábado idêntico
    current = TrainingPlan(
        athlete_name="Mauricio", objective="x", phase="BUILD",
        weekly_volume=24.0, running_days=["Tuesday", "Saturday"],
        week_start=WEEK_START,
        sessions=[
            make_planned_session(
                day="Tuesday", workout_type="Fartlek",
                target_pace_min="5:00", target_pace_max="5:20",
            ),
            make_planned_session(
                day="Saturday", workout_type="Longão",
                planned_distance_km=9.0,
                target_pace_min="6:20", target_pace_max="6:50",
            ),
        ],
    )
    pushed = _plan("6:20", "6:50")  # sábado igual; terça sem pace

    outbox, offer = _run(current=current, pushed=pushed)

    outbox.send.assert_not_awaited()
    offer.clear.assert_called_once_with("mauricio")
