import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.review.wellbeing_followup_notifier import (
    WellbeingFollowUpNotifier,
)
from tests.coach.factories import make_runner

MOD = "app.application.review.wellbeing_followup_notifier"

TODAY = date(2026, 8, 16)


def _run(hour, concern, already_sent=False):

    runner = make_runner(name="Renato", phone="+5511900000001")

    with (
        patch(f"{MOD}.RunnerProfileRepository") as repo_cls,
        patch(f"{MOD}.LoadRunnerProfile") as load_runner,
        patch(f"{MOD}.CheckinRepository") as checkin_cls,
        patch(f"{MOD}.DispatchGuard") as guard,
        patch(f"{MOD}.CoachOutbox") as outbox,
        patch(f"{MOD}.now_in",
              return_value=SimpleNamespace(hour=hour, date=lambda: TODAY)),
        patch(f"{MOD}.today_local", return_value=TODAY),
        patch(f"{MOD}.use_athlete_timezone"),
    ):

        repo_cls.return_value.list_all.return_value = ["renato"]
        load_runner.execute.return_value = runner
        checkin_cls.return_value.recent_concern.return_value = concern
        guard.already_sent.return_value = already_sent
        outbox.send = AsyncMock()

        asyncio.run(WellbeingFollowUpNotifier.notify_all())

        return outbox, guard


def _concern(day, illness=False, soreness=None, note=""):

    return SimpleNamespace(day=day, illness=illness, soreness=soreness, note=note)


def test_follows_up_on_illness_after_delay():

    outbox, guard = _run(
        hour=12, concern=_concern("2026-08-13", illness=True),  # 3 dias atrás
    )

    outbox.send.assert_awaited_once()
    _, msg = outbox.send.await_args.args
    assert "doente" in msg or "gripe" in msg
    guard.mark.assert_called_once()


def test_follows_up_on_pain_with_location():

    outbox, _ = _run(
        hour=12, concern=_concern("2026-08-13", soreness=4, note="joelho"),
    )

    outbox.send.assert_awaited_once()
    _, msg = outbox.send.await_args.args
    assert "joelho" in msg


def test_silent_outside_hour():

    outbox, _ = _run(hour=9, concern=_concern("2026-08-13", illness=True))

    outbox.send.assert_not_awaited()


def test_too_soon_does_not_follow_up():
    """Queixa de ONTEM ainda não é acompanhada (dia 0-1 já teve o descanso)."""

    outbox, _ = _run(hour=12, concern=_concern("2026-08-15", illness=True))

    outbox.send.assert_not_awaited()


def test_no_concern_stays_quiet():

    outbox, _ = _run(hour=12, concern=None)

    outbox.send.assert_not_awaited()


def test_dedup_one_touch_per_episode():

    outbox, _ = _run(
        hour=12, concern=_concern("2026-08-13", illness=True), already_sent=True,
    )

    outbox.send.assert_not_awaited()
