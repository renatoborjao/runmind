from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.application.garmin.garmin_activity_poller import (
    GarminActivityPoller,
)
from app.application.strava.strava_activity_catchup import (
    StravaActivityCatchup,
)
from app.application.planner.morning_briefing_notifier import (
    MorningBriefingNotifier,
)
from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from app.core.clock import DEFAULT_TIMEZONE
from app.core.config import get_settings
from app.infrastructure.backup.storage_backup import StorageBackup
from app.infrastructure.integrations.evolution.connection_watchdog import (
    ConnectionWatchdog,
)

_scheduler: AsyncIOScheduler | None = None

# tolerância dos jobs de INTERVALO (poll/catch-up/watchdog): o event loop fica
# ocupado por 1-2s processando webhook/análise/Telegram, e a graça padrão do
# APScheduler é 1s -> o tick era PULADO e logava "missed by 0:00:02". 5 min de
# folga faz o job rodar mesmo com o loop ocupado, sem ruído no log.
_INTERVAL_GRACE = 300


async def _watchdog_tick() -> None:

    try:

        await ConnectionWatchdog.check_and_heal()

    except Exception as e:

        # Evolution fora do ar etc. — só loga, tenta de novo em 5 min
        print(f"Watchdog do WhatsApp falhou: {e}")


async def _garmin_poll_tick() -> None:

    try:

        await GarminActivityPoller.poll_all()

    except Exception as e:

        # Garmin fora do ar / token expirado — só loga, tenta em 10 min
        print(f"Garmin poll falhou: {e}")


async def _strava_catchup_tick() -> None:

    try:

        await StravaActivityCatchup.run_all()

    except Exception as e:

        # Strava fora do ar / rate limit — só loga, tenta na próxima passada
        print(f"Strava catch-up falhou: {e}")


def _backup_tick() -> None:

    try:

        settings = get_settings()

        path = StorageBackup(
            backup_dir=settings.backup_dir or None,
            keep=settings.backup_keep,
        ).run()

        if path is not None:

            print(f"Backup do storage: {path.name}")

    except Exception as e:

        # backup nunca pode derrubar o app — só loga, tenta na próxima
        print(f"Backup do storage falhou: {e}")


def start_weekly_plan_scheduler() -> AsyncIOScheduler:

    global _scheduler

    if _scheduler is not None:

        return _scheduler

    _scheduler = AsyncIOScheduler(
        timezone=DEFAULT_TIMEZONE.key,
    )

    # MULTI-FUSO: os jobs abaixo rodam de HORA EM HORA; cada notifier decide,
    # por atleta, se é o horário LOCAL de enviar (domingo 15h/20h, segunda 8h,
    # 06h diário no fuso DELE) e faz dedup pra não repetir. Assim o amigo de
    # Portugal recebe no horário de Lisboa, não no do Brasil.

    # Entrega do plano — domingo 15h local (gate no WeeklyPlanNotifier).
    _scheduler.add_job(
        WeeklyPlanNotifier.notify_all,
        trigger="cron",
        minute=0,
        misfire_grace_time=3600,
        id="weekly_plan_notification",
    )

    # Review — domingo 20h local (fecha a semana ISO inteira).
    _scheduler.add_job(
        WeeklyReviewNotifier.notify_all,
        trigger="cron",
        minute=0,
        misfire_grace_time=3600,
        id="weekly_review_notification",
    )

    # Reforço do treinador externo — segunda 8h local.
    _scheduler.add_job(
        WeeklyPlanNotifier.remind_external_pending,
        trigger="cron",
        minute=0,
        misfire_grace_time=3600,
        id="external_plan_reminder",
    )

    # Briefing matinal — 06h local: furo de ONTEM (se houve) + treino de HOJE
    # numa mensagem só. Descanso sem furo não envia nada.
    _scheduler.add_job(
        MorningBriefingNotifier.notify_all,
        trigger="cron",
        minute=0,
        misfire_grace_time=3600,
        id="morning_briefing",
    )

    # autocura da sessão do WhatsApp (quedas transitórias) — só quando
    # o canal está ligado; com WHATSAPP_ENABLED=false não fica batendo
    # numa Evolution desligada a cada 5 min
    if get_settings().whatsapp_enabled:

        _scheduler.add_job(
            _watchdog_tick,
            trigger="interval",
            minutes=5,
            misfire_grace_time=_INTERVAL_GRACE,
            id="whatsapp_connection_watchdog",
        )

    # Garmin não tem webhook: detecta treino novo por polling (~10 min).
    # Barato quando ninguém tem Garmin (só checa arquivo de token).
    _scheduler.add_job(
        _garmin_poll_tick,
        trigger="interval",
        minutes=10,
        misfire_grace_time=_INTERVAL_GRACE,
        id="garmin_activity_poll",
    )

    # Rede de segurança do webhook Strava (atleta só-Strava): roda LOGO no
    # startup (recupera o feedback perdido enquanto o servidor esteve fora) e
    # a cada 15 min (cobre entregas que o Strava perdeu). Dedup pelo mesmo
    # guard do webhook — não reprocessa o que já saiu.
    _scheduler.add_job(
        _strava_catchup_tick,
        trigger="interval",
        minutes=15,
        misfire_grace_time=_INTERVAL_GRACE,
        id="strava_activity_catchup",
        next_run_time=datetime.now(DEFAULT_TIMEZONE),
    )

    # Backup do storage — snapshot .zip dos dados dos atletas. A cada 6h e
    # UM logo no startup (next_run_time), pra sempre haver cópia recente
    # mesmo numa máquina que dorme (interval roda quando ela está ligada).
    if get_settings().backup_enabled:

        _scheduler.add_job(
            _backup_tick,
            trigger="interval",
            hours=6,
            misfire_grace_time=_INTERVAL_GRACE,
            id="storage_backup",
            next_run_time=datetime.now(DEFAULT_TIMEZONE),
        )

    _scheduler.start()

    return _scheduler


def stop_weekly_plan_scheduler() -> None:

    global _scheduler

    if _scheduler is not None:

        _scheduler.shutdown()

        _scheduler = None
