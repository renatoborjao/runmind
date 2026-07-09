from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from app.core.clock import DEFAULT_TIMEZONE
from app.core.config import get_settings
from app.infrastructure.integrations.evolution.connection_watchdog import (
    ConnectionWatchdog,
)

_scheduler: AsyncIOScheduler | None = None


async def _watchdog_tick() -> None:

    try:

        await ConnectionWatchdog.check_and_heal()

    except Exception as e:

        # Evolution fora do ar etc. — só loga, tenta de novo em 5 min
        print(f"Watchdog do WhatsApp falhou: {e}")


def start_weekly_plan_scheduler() -> AsyncIOScheduler:

    global _scheduler

    if _scheduler is not None:

        return _scheduler

    _scheduler = AsyncIOScheduler(
        timezone=DEFAULT_TIMEZONE.key,
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

    # 06h todo dia: lembrete do treino do dia (dia de descanso não envia)
    _scheduler.add_job(
        DailyTrainingNotifier.notify_all,
        trigger="cron",
        hour=6,
        minute=0,
        misfire_grace_time=3600,
        id="daily_training_reminder",
    )

    # autocura da sessão do WhatsApp (quedas transitórias) — só quando
    # o canal está ligado; com WHATSAPP_ENABLED=false não fica batendo
    # numa Evolution desligada a cada 5 min
    if get_settings().whatsapp_enabled:

        _scheduler.add_job(
            _watchdog_tick,
            trigger="interval",
            minutes=5,
            id="whatsapp_connection_watchdog",
        )

    _scheduler.start()

    return _scheduler


def stop_weekly_plan_scheduler() -> None:

    global _scheduler

    if _scheduler is not None:

        _scheduler.shutdown()

        _scheduler = None
