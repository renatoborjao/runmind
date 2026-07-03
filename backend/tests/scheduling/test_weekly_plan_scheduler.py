from unittest.mock import MagicMock, patch

import app.infrastructure.scheduling.weekly_plan_scheduler as scheduler_module

MODULE = "app.infrastructure.scheduling.weekly_plan_scheduler"


def _reset_module_state():

    scheduler_module._scheduler = None


def test_registers_cron_job_for_sunday_15h():

    _reset_module_state()

    with patch(f"{MODULE}.AsyncIOScheduler") as mock_scheduler_cls:

        mock_instance = MagicMock()

        mock_scheduler_cls.return_value = mock_instance

        scheduler_module.start_weekly_plan_scheduler()

        _, kwargs = mock_instance.add_job.call_args

        assert kwargs["trigger"] == "cron"
        assert kwargs["day_of_week"] == "sun"
        assert kwargs["hour"] == 15
        assert kwargs["minute"] == 0

        mock_instance.start.assert_called_once()

    _reset_module_state()


def test_start_is_idempotent():

    _reset_module_state()

    with patch(f"{MODULE}.AsyncIOScheduler") as mock_scheduler_cls:

        mock_instance = MagicMock()

        mock_scheduler_cls.return_value = mock_instance

        first = scheduler_module.start_weekly_plan_scheduler()
        second = scheduler_module.start_weekly_plan_scheduler()

        assert first is second

        mock_scheduler_cls.assert_called_once()

    _reset_module_state()


def test_stop_shuts_down_and_clears_state():

    _reset_module_state()

    with patch(f"{MODULE}.AsyncIOScheduler") as mock_scheduler_cls:

        mock_instance = MagicMock()

        mock_scheduler_cls.return_value = mock_instance

        scheduler_module.start_weekly_plan_scheduler()

        scheduler_module.stop_weekly_plan_scheduler()

        mock_instance.shutdown.assert_called_once()

        assert scheduler_module._scheduler is None
