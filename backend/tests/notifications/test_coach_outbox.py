import asyncio
from unittest.mock import AsyncMock, patch

from app.application.notifications.coach_outbox import CoachOutbox
from app.infrastructure.persistence.coach_outbox_repository import (
    CoachOutboxRepository,
)
from tests.coach.factories import make_runner

MODULE = "app.application.notifications.coach_outbox"


def _repo(tmp_path) -> CoachOutboxRepository:

    repo = CoachOutboxRepository()
    repo.storage = tmp_path
    return repo


def test_append_and_recent(tmp_path):

    repo = _repo(tmp_path)

    repo.append("renato", "msg1")
    repo.append("renato", "msg2")

    assert [e["text"] for e in repo.recent("renato", 5)] == ["msg1", "msg2"]


def test_recent_caps_history_and_returns_last(tmp_path):

    repo = _repo(tmp_path)

    for i in range(15):

        repo.append("renato", f"m{i}")

    # guarda no máximo 10; recent(3) devolve os 3 últimos
    assert [e["text"] for e in repo.recent("renato", 3)] == ["m12", "m13", "m14"]


def test_recent_empty_for_unknown_profile(tmp_path):

    assert _repo(tmp_path).recent("ninguem", 3) == []


def test_send_delivers_and_records():
    """Envia pelo NotificationService E registra no outbox (pelo id)."""

    runner = make_runner(id="renato")

    with (
        patch(f"{MODULE}.NotificationService") as notif,
        patch(f"{MODULE}.CoachOutboxRepository") as repo_cls,
    ):

        notif.send = AsyncMock()

        asyncio.run(CoachOutbox.send(runner, "análise do treino"))

        notif.send.assert_awaited_once_with(runner, "análise do treino")

        repo_cls.return_value.append.assert_called_once()
        assert repo_cls.return_value.append.call_args.args[0] == "renato"


def test_send_survives_record_failure():
    """Falha ao registrar no outbox nunca derruba o envio já feito."""

    runner = make_runner(id="renato")

    with (
        patch(f"{MODULE}.NotificationService") as notif,
        patch(f"{MODULE}.CoachOutboxRepository") as repo_cls,
    ):

        notif.send = AsyncMock()
        repo_cls.return_value.append.side_effect = OSError("disco cheio")

        # não levanta
        asyncio.run(CoachOutbox.send(runner, "msg"))

        notif.send.assert_awaited_once()
