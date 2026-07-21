from types import SimpleNamespace
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


def test_backup_tick_skips_when_a_recent_snapshot_already_exists():
    """Restart rápido (hot-reload do uvicorn em dev) não deve duplicar o
    snapshot — só o backup_now.py manual força incondicionalmente."""

    fake_settings = SimpleNamespace(backup_dir="", backup_keep=28)

    with patch(f"{MODULE}.get_settings", return_value=fake_settings), \
         patch(f"{MODULE}.StorageBackup") as mock_cls:

        mock_backup = MagicMock()
        mock_backup.has_recent_snapshot.return_value = True
        mock_cls.return_value = mock_backup

        scheduler_module._backup_tick()

        mock_backup.has_recent_snapshot.assert_called_once_with(
            scheduler_module._MIN_BACKUP_INTERVAL
        )
        mock_backup.run.assert_not_called()


def test_backup_tick_runs_when_no_recent_snapshot():

    fake_settings = SimpleNamespace(backup_dir="", backup_keep=28)

    with patch(f"{MODULE}.get_settings", return_value=fake_settings), \
         patch(f"{MODULE}.StorageBackup") as mock_cls:

        mock_backup = MagicMock()
        mock_backup.has_recent_snapshot.return_value = False
        mock_backup.run.return_value = None
        mock_cls.return_value = mock_backup

        scheduler_module._backup_tick()

        mock_backup.run.assert_called_once()
