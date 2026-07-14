import asyncio
from unittest.mock import AsyncMock, patch

from app.application.planner.morning_briefing_notifier import (
    MorningBriefingNotifier,
)
from tests.coach.factories import make_runner

MODULE = "app.application.planner.morning_briefing_notifier"

RUNNER = make_runner()


def _run(missed, today):

    sent = {}

    with (
        patch(f"{MODULE}.MissedWorkoutFlow") as flow,
        patch(f"{MODULE}.DailyTrainingNotifier") as daily,
        patch(f"{MODULE}.CoachOutbox") as notifier,
    ):

        flow.process = AsyncMock(
            return_value=(RUNNER, missed) if missed else None
        )
        daily.build = AsyncMock(
            return_value=(RUNNER, today) if today else None
        )

        async def _capture(runner, message):
            sent["runner"] = runner
            sent["message"] = message

        notifier.send = AsyncMock(side_effect=_capture)

        asyncio.run(MorningBriefingNotifier._notify_one("renato"))

    return sent


def test_miss_and_today_go_in_one_message_furo_first():

    sent = _run(missed="Furou ontem — quer que eu ajuste?", today="🏃 Hoje: 8km")

    # um envio só, furo primeiro depois hoje
    assert sent["message"] == (
        "Furou ontem — quer que eu ajuste?\n\n🏃 Hoje: 8km"
    )


def test_only_the_miss_when_today_is_rest():

    sent = _run(missed="Furou ontem, mas segue igual. 💪", today=None)

    assert sent["message"] == "Furou ontem, mas segue igual. 💪"


def test_only_today_when_there_was_no_miss():

    sent = _run(missed=None, today="🏃 Hoje: tiros 6x800")

    assert sent["message"] == "🏃 Hoje: tiros 6x800"


def test_nothing_sent_when_no_miss_and_rest_day():

    sent = _run(missed=None, today=None)

    assert sent == {}
