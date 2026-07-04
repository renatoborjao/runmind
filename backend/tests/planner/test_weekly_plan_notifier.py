import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.planner.weekly_plan_notifier"


def _external_plan(week_start: date) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Fulano",
        objective="10k",
        phase="EXTERNO",
        weekly_volume=20.0,
        running_days=["Tuesday"],
        week_start=week_start,
        sessions=[],
        source="externo",
    )


def _run_external(plan):

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_plan_repo_cls,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.NotificationService") as mock_notification,
    ):

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = ["fulano"]
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.return_value = make_runner(
            name="Fulano",
            phone="+5511900000009",
            external_coach=True,
        )

        mock_plan_repo_cls.return_value.load.return_value = plan

        mock_formatter.format.return_value = "plano formatado"

        mock_notification.send = AsyncMock()

        asyncio.run(WeeklyPlanNotifier.notify_all())

        return mock_notification, mock_formatter


def test_external_coach_with_current_plan_gets_it_formatted():

    current_week = WeeklyPlanService._week_start(today_local())

    mock_notification, mock_formatter = _run_external(
        _external_plan(current_week),
    )

    mock_formatter.format.assert_called_once()

    assert mock_notification.send.call_args.args[1] == "plano formatado"


def test_external_coach_without_current_plan_gets_reminder():

    stale_week = date(2020, 1, 6)

    mock_notification, mock_formatter = _run_external(
        _external_plan(stale_week),
    )

    mock_formatter.format.assert_not_called()

    assert "print" in mock_notification.send.call_args.args[1]


def test_notify_all_sends_to_every_profile():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder"),
        patch(f"{MODULE}.MetricsResolver"),
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

        mock_notification.send = AsyncMock()

        asyncio.run(WeeklyPlanNotifier.notify_all())

        assert mock_notification.send.await_count == 2

        sent = [
            call.args
            for call in mock_notification.send.await_args_list
        ]
        assert {r.name for r, _ in sent} == {"Renato", "Camila"}
        assert all(msg == "mensagem" for _, msg in sent)


def test_notify_all_continues_after_one_profile_fails():

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder"),
        patch(f"{MODULE}.MetricsResolver"),
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

        mock_notification.send = AsyncMock()

        asyncio.run(WeeklyPlanNotifier.notify_all())

        mock_notification.send.assert_awaited_once()
        runner, msg = mock_notification.send.await_args.args
        assert runner.name == "Renato"
        assert msg == "mensagem"
