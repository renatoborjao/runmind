from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from app.application.review.weekly_review_notifier import WeeklyReviewNotifier

_scheduler: AsyncIOScheduler | None = None


def start_weekly_plan_scheduler() -> AsyncIOScheduler:

    global _scheduler

    if _scheduler is not None:

        return _scheduler

    _scheduler = AsyncIOScheduler(
        timezone="America/Sao_Paulo",
    )

    _scheduler.add_job(
        WeeklyPlanNotifier.notify_all,
        trigger="cron",
        day_of_week="sun",
        hour=15,
        minute=0,
        misfire_grace_time=3600,
        id="weekly_plan_notification",
    )

    # 20h fecha a semana ISO inteira (pega o long run de domingo)
    _scheduler.add_job(
        WeeklyReviewNotifier.notify_all,
        trigger="cron",
        day_of_week="sun",
        hour=20,
        minute=0,
        misfire_grace_time=3600,
        id="weekly_review_notification",
    )

    _scheduler.start()

    return _scheduler


def stop_weekly_plan_scheduler() -> None:

    global _scheduler

    if _scheduler is not None:

        _scheduler.shutdown()

        _scheduler = None
