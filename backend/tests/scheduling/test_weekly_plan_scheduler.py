from unittest.mock import MagicMock, patch

import app.infrastructure.scheduling.weekly_plan_scheduler as scheduler_module

MODULE = "app.infrastructure.scheduling.weekly_plan_scheduler"


def _reset_module_state():

    scheduler_module._scheduler = None


def test_registers_hourly_notifier_jobs_for_multi_timezone():
    """Multi-fuso: os jobs de notificação rodam de HORA EM HORA (minute=0, sem
    dia/hora fixos); cada notifier decide o horário LOCAL do atleta."""

    _reset_module_state()

    with patch(f"{MODULE}.AsyncIOScheduler") as mock_scheduler_cls:

        mock_instance = MagicMock()

        mock_scheduler_cls.return_value = mock_instance

        scheduler_module.start_weekly_plan_scheduler()

        jobs = {
            kwargs["id"]: kwargs
            for _, kwargs in mock_instance.add_job.call_args_list
        }

        for job_id in (
            "weekly_plan_notification",
            "weekly_review_notification",
            "external_plan_reminder",
            "morning_briefing",
        ):

            job = jobs[job_id]
            assert job["trigger"] == "cron"
            assert job["minute"] == 0
            # de hora em hora: sem dia/hora fixos (o gate local resolve)
            assert "day_of_week" not in job
            assert "hour" not in job

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
