import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from tests.coach.factories import make_runner

MODULE = "app.application.review.weekly_review_notifier"


def _run_notify_all(profiles, runners, messages):

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.WeeklyReviewBuilder"),
        patch(f"{MODULE}.WeeklyReviewMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.NotificationService") as mock_notification,
    ):

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = profiles
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.side_effect = runners

        mock_load_history.execute = AsyncMock(return_value=object())

        mock_formatter.format.side_effect = messages

        mock_notification.send_training_feedback = AsyncMock()

        asyncio.run(WeeklyReviewNotifier.notify_all())

        return mock_notification


def test_notify_all_sends_review_to_every_profile():

    mock_notification = _run_notify_all(
        profiles=["renato", "camila"],
        runners=[
            make_runner(name="Renato", phone="+5511900000001"),
            make_runner(name="Camila", phone="+5511900000002"),
        ],
        messages=["resumo renato", "resumo camila"],
    )

    assert mock_notification.send_training_feedback.await_count == 2

    mock_notification.send_training_feedback.assert_any_await(
        phone="+5511900000001",
        message="resumo renato",
    )


def test_does_not_send_when_formatter_returns_none():

    mock_notification = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato", phone="+5511900000001")],
        messages=[None],
    )

    mock_notification.send_training_feedback.assert_not_awaited()


def test_notify_all_continues_after_one_profile_fails():

    mock_notification = _run_notify_all(
        profiles=["quebrado", "renato"],
        runners=[
            Exception("perfil corrompido"),
            make_runner(name="Renato", phone="+5511900000001"),
        ],
        messages=["resumo renato"],
    )

    mock_notification.send_training_feedback.assert_awaited_once_with(
        phone="+5511900000001",
        message="resumo renato",
    )
