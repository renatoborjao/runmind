import asyncio
from unittest.mock import AsyncMock, patch

from app.application.monitoring import ai_health_monitor as module
from app.application.monitoring.ai_health_monitor import (
    AIHealthMonitor,
    FAILURE_THRESHOLD,
)
from app.infrastructure.persistence import ai_health_repository as repo_module

MODULE = "app.application.monitoring.ai_health_monitor"


def _isolate(tmp_path, monkeypatch, admin="123"):

    monkeypatch.setattr(repo_module, "_STORAGE", tmp_path / "storage")

    settings = type("S", (), {"admin_telegram_id": admin})()

    monkeypatch.setattr(module, "get_settings", lambda: settings)


def _sends():

    return patch(
        f"{MODULE}.NotificationService.send_to",
        new=AsyncMock(),
    )


def test_failures_below_threshold_do_not_alert(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch)

    with _sends() as send:

        for _ in range(FAILURE_THRESHOLD - 1):

            asyncio.run(AIHealthMonitor.record_failure("400 boom"))

    send.assert_not_awaited()


def test_alerts_once_when_threshold_crossed(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch)

    with _sends() as send:

        for _ in range(FAILURE_THRESHOLD + 2):

            asyncio.run(AIHealthMonitor.record_failure("400 INVALID_ARGUMENT"))

    # cruzou o limiar uma vez só, mesmo com falhas a mais depois
    assert send.await_count == 1

    msg = send.await_args.kwargs["message"]

    assert "400 INVALID_ARGUMENT" in msg


def test_success_after_alert_notifies_recovery(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch)

    with _sends() as send:

        for _ in range(FAILURE_THRESHOLD):

            asyncio.run(AIHealthMonitor.record_failure("fora do ar"))

        asyncio.run(AIHealthMonitor.record_success())

    # 1 alerta de falha + 1 de recuperação
    assert send.await_count == 2

    assert "normalmente" in send.await_args.kwargs["message"]


def test_success_while_healthy_is_silent(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch)

    with _sends() as send:

        asyncio.run(AIHealthMonitor.record_success())

    send.assert_not_awaited()


def test_success_resets_counter(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch)

    with _sends() as send:

        # falha abaixo do limiar, recupera, e recomeça a contar do zero
        asyncio.run(AIHealthMonitor.record_failure("x"))

        asyncio.run(AIHealthMonitor.record_success())

        for _ in range(FAILURE_THRESHOLD - 1):

            asyncio.run(AIHealthMonitor.record_failure("x"))

    # sem alerta: o sucesso zerou, então não chegou no limiar de novo
    send.assert_not_awaited()


def test_no_admin_configured_sends_nothing(tmp_path, monkeypatch):

    _isolate(tmp_path, monkeypatch, admin="")

    with _sends() as send:

        for _ in range(FAILURE_THRESHOLD + 1):

            asyncio.run(AIHealthMonitor.record_failure("boom"))

    send.assert_not_awaited()
