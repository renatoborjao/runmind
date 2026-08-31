import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from app.application.coach.intelligence.coach_reconcile_notifier import (
    CoachReconcileNotifier,
)

MOD = "app.application.coach.intelligence.coach_reconcile_notifier"


def _runner():

    return SimpleNamespace(
        id="helio", name="Hélio", timezone="America/Sao_Paulo",
        goal="saúde", target_race=None, target_time=None, race_date=None,
        preferred_running_days=["Monday", "Wednesday", "Saturday"],
    )


def _acts_over():
    """4,4,3,4 nas últimas 4 semanas -> rotina 'over'."""

    monday = date(2026, 8, 3)
    acts = []
    for w, n in enumerate([4, 4, 3, 4]):
        wk = monday + timedelta(days=7 * w)
        for r in range(n):
            d = (wk + timedelta(days=r)).isoformat()
            acts.append(SimpleNamespace(start_date=d, start_date_local=d,
                                        distance=6000.0))
    return acts


def _run(active: bool):

    sent = []

    settings = SimpleNamespace(
        coach_reconcile_active_for=lambda p: active,
    )

    guard = MagicMock()
    guard.already_sent.return_value = False

    history = SimpleNamespace(activities=_acts_over())

    with (
        patch(f"{MOD}.get_settings", return_value=settings),
        patch(f"{MOD}.RunnerProfileRepository") as repo,
        patch(f"{MOD}.LoadRunnerProfile.execute", return_value=_runner()),
        patch(f"{MOD}.LoadTrainingHistory.execute",
              new=AsyncMock(return_value=history)),
        patch(f"{MOD}.DispatchGuard", guard),
        patch(f"{MOD}.use_athlete_timezone"),
        patch(f"{MOD}.now_in",
              return_value=datetime(2026, 8, 31, 10, 0,
                                    tzinfo=ZoneInfo("America/Sao_Paulo"))),
        patch(f"{MOD}.CoachOutbox.send",
              new=AsyncMock(side_effect=lambda *a, **k: sent.append((a, k)))),
    ):
        repo.return_value.list_all.return_value = ["helio"]
        asyncio.run(CoachReconcileNotifier.notify_all())

    return sent


def test_flag_off_sends_nothing():
    """A garantia: DESLIGADA, nada sai pra atleta."""

    assert _run(active=False) == []


def test_flag_on_asks_frequency_for_routine_over():
    """Ligada + rotina 'over' -> pergunta de oficializar o dia."""

    sent = _run(active=True)

    assert len(sent) == 1
    message = sent[0][0][1]
    assert "dias" in message and "Hélio" in message
    assert sent[0][1].get("kind") == "reconcile"
