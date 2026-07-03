import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from tests.coach.factories import make_runner

MODULE = "app.application.planner.weekly_plan_notifier"


def test_notify_all_sends_to_every_profile():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder"),
        patch(f"{MODULE}.RunnerMetricsBuilder"),
        patch(f"{MODULE}.WeeklyPlanService"),
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.NotificationService") as mock_notification,
    ):

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = ["renato", "camila"]
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.side_effect = [
            make_runner(name="Renato", phone="+5511900000001"),
            make_runner(name="Camila", phone="+5511900000002"),
        ]

        mock_load_history.execute = AsyncMock(return_value=object())

        mock_formatter.format.return_value = "mensagem"

        mock_notification.send_training_feedback = AsyncMock()

        asyncio.run(WeeklyPlanNotifier.notify_all())

        assert mock_notification.send_training_feedback.await_count == 2

        mock_notification.send_training_feedback.assert_any_await(
            phone="+5511900000001",
            message="mensagem",
        )

        mock_notification.send_training_feedback.assert_any_await(
            phone="+5511900000002",
            message="mensagem",
        )


def test_notify_all_continues_after_one_profile_fails():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder"),
        patch(f"{MODULE}.RunnerMetricsBuilder"),
        patch(f"{MODULE}.WeeklyPlanService"),
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.NotificationService") as mock_notification,
    ):

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = ["quebrado", "renato"]
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.side_effect = [
            Exception("perfil corrompido"),
            make_runner(name="Renato", phone="+5511900000001"),
        ]

        mock_load_history.execute = AsyncMock(return_value=object())

        mock_formatter.format.return_value = "mensagem"

        mock_notification.send_training_feedback = AsyncMock()

        asyncio.run(WeeklyPlanNotifier.notify_all())

        mock_notification.send_training_feedback.assert_awaited_once_with(
            phone="+5511900000001",
            message="mensagem",
        )
