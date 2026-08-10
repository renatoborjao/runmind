import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.history.silence_detector import SilenceVerdict
from app.application.review.reengagement_notifier import ReengagementNotifier
from tests.coach.factories import make_runner

MODULE = "app.application.review.reengagement_notifier"


def _run(hour, verdict, already_sent=False):

    runner = make_runner(name="Renato", phone="+5511900000001")

    history = MagicMock()
    history.activities = []

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.ConversationRepository"),
        patch(f"{MODULE}.SilenceDetector") as mock_detector,
        patch(f"{MODULE}.DispatchGuard") as mock_guard,
        patch(f"{MODULE}.BuildTrainingGoal"),
        patch(f"{MODULE}.ReengagementWriter") as mock_writer,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(
            f"{MODULE}.now_in",
            return_value=datetime(2026, 8, 10, hour, 0),
        ),
        patch(f"{MODULE}.use_athlete_timezone"),
    ):

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = ["renato"]
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.return_value = runner

        mock_load_history.execute = AsyncMock(return_value=history)

        mock_detector.assess.return_value = verdict

        mock_guard.already_sent.return_value = already_sent

        mock_writer.facts.return_value = "fatos"
        mock_writer.write = AsyncMock(return_value="ei, senti sua falta!")

        mock_outbox.send = AsyncMock()

        asyncio.run(ReengagementNotifier.notify_all())

        return mock_outbox, mock_guard


_DARK = SilenceVerdict(
    is_dark=True,
    days_silent=9,
    last_active=None,
    typical_gap_days=2.5,
    threshold_days=6,
)

_LIGHT = SilenceVerdict(
    is_dark=False,
    days_silent=1,
    last_active=None,
    typical_gap_days=2.5,
    threshold_days=6,
)


def test_sends_nudge_when_dark_at_local_hour():

    mock_outbox, mock_guard = _run(hour=17, verdict=_DARK)

    mock_outbox.send.assert_awaited_once()
    mock_guard.mark.assert_called_once()


def test_silent_outside_local_hour():

    mock_outbox, _ = _run(hour=9, verdict=_DARK)

    mock_outbox.send.assert_not_awaited()


def test_no_nudge_when_not_dark():

    mock_outbox, _ = _run(hour=17, verdict=_LIGHT)

    mock_outbox.send.assert_not_awaited()


def test_dedup_one_touch_per_episode():
    """Já cutucado neste episódio → não repete (orientar, não repetir)."""

    mock_outbox, mock_guard = _run(hour=17, verdict=_DARK, already_sent=True)

    mock_outbox.send.assert_not_awaited()
    mock_guard.mark.assert_not_called()
