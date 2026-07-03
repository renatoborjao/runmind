from unittest.mock import MagicMock, patch

import app.infrastructure.scheduling.weekly_plan_scheduler as scheduler_module

MODULE = "app.infrastructure.scheduling.weekly_plan_scheduler"


def _reset_module_state():

    scheduler_module._scheduler = None


def test_registers_plan_and_review_cron_jobs():

    _reset_module_state()

    with patch(f"{MODULE}.AsyncIOScheduler") as mock_scheduler_cls:

        mock_instance = MagicMock()

        mock_scheduler_cls.return_value = mock_instance

        scheduler_module.start_weekly_plan_scheduler()

        jobs = {
            kwargs["id"]: kwargs
            for _, kwargs in mock_instance.add_job.call_args_list
        }

        plan = jobs["weekly_plan_notification"]
        assert plan["trigger"] == "cron"
        assert plan["day_of_week"] == "sun"
        assert plan["hour"] == 15
        assert plan["minute"] == 0

        review = jobs["weekly_review_notification"]
        assert review["trigger"] == "cron"
        assert review["day_of_week"] == "sun"
        assert review["hour"] == 20
        assert review["minute"] == 0

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
