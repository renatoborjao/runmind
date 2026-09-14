import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.notifications.app_inbox import AppInbox, _push_body, _title_for
from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)
from app.infrastructure.persistence.push_subscription_repository import (
    PushSubscriptionRepository,
)
from tests.coach.factories import make_runner

MODULE = "app.application.notifications.app_inbox"


# ---------- AppNotificationRepository ----------


def _notif_repo(tmp_path) -> AppNotificationRepository:

    repo = AppNotificationRepository()
    repo.storage = tmp_path
    return repo


def test_append_puts_newest_first_and_unread(tmp_path):

    repo = _notif_repo(tmp_path)

    repo.append("renato2", "primeira", title="A", kind="feedback")
    repo.append("renato2", "segunda", title="B", kind="weekly_plan")

    items = repo.load("renato2")

    assert [i["text"] for i in items] == ["segunda", "primeira"]
    assert repo.unread_count("renato2") == 2


def test_mark_read_all_and_specific(tmp_path):

    repo = _notif_repo(tmp_path)

    a = repo.append("renato2", "a")
    repo.append("renato2", "b")

    # marca só uma
    repo.mark_read("renato2", [a["id"]])
    assert repo.unread_count("renato2") == 1

    # marca todas
    repo.mark_read("renato2")
    assert repo.unread_count("renato2") == 0


def test_unknown_profile_is_empty(tmp_path):

    assert _notif_repo(tmp_path).load("ninguem") == []
    assert _notif_repo(tmp_path).unread_count("ninguem") == 0


# ---------- PushSubscriptionRepository ----------


def _push_repo(tmp_path) -> PushSubscriptionRepository:

    repo = PushSubscriptionRepository()
    repo.storage = tmp_path
    return repo


def test_push_add_dedups_by_endpoint(tmp_path):

    repo = _push_repo(tmp_path)

    repo.add("renato2", {"endpoint": "https://push/1", "keys": {"a": "1"}})
    repo.add("renato2", {"endpoint": "https://push/1", "keys": {"a": "2"}})
    repo.add("renato2", {"endpoint": "https://push/2", "keys": {}})

    subs = repo.list("renato2")

    assert len(subs) == 2
    # o segundo add do mesmo endpoint substitui as keys
    one = next(s for s in subs if s["endpoint"] == "https://push/1")
    assert one["keys"] == {"a": "2"}


def test_push_remove(tmp_path):

    repo = _push_repo(tmp_path)

    repo.add("renato2", {"endpoint": "https://push/1"})
    repo.remove("renato2", "https://push/1")

    assert repo.list("renato2") == []


def test_push_add_without_endpoint_is_ignored(tmp_path):

    repo = _push_repo(tmp_path)

    repo.add("renato2", {"keys": {"a": "1"}})

    assert repo.list("renato2") == []


# ---------- title / body helpers ----------


def test_title_for_known_and_unknown():

    assert _title_for("feedback") == "Análise do seu treino"
    assert _title_for("desconhecido") == "Mensagem do coach"
    assert _title_for(None) == "Mensagem do coach"


def test_push_body_truncates_long_text():

    body = _push_body("x" * 500)

    assert len(body) <= 140
    assert body.endswith("…")


# ---------- AppInbox.deliver ----------


def test_deliver_appends_and_pushes():

    runner = make_runner(id="renato2")

    with (
        patch(f"{MODULE}.AppNotificationRepository") as repo_cls,
        patch(f"{MODULE}.WebPushSender") as push,
    ):

        repo = MagicMock()
        repo_cls.return_value = repo

        asyncio.run(AppInbox.deliver(runner, "seu treino de hoje", kind="daily_training"))

        repo.append.assert_called_once()
        assert repo.append.call_args.args[0] == "renato2"
        assert repo.append.call_args.kwargs["kind"] == "daily_training"
        assert repo.append.call_args.kwargs["title"] == "Seu treino de hoje"

        push.send.assert_called_once()
        assert push.send.call_args.args[0] == "renato2"


def test_deliver_survives_repo_failure():
    """Falhar na central nunca derruba o envio já feito no canal."""

    runner = make_runner(id="renato2")

    with (
        patch(f"{MODULE}.AppNotificationRepository") as repo_cls,
        patch(f"{MODULE}.WebPushSender") as push,
    ):

        repo_cls.return_value.append.side_effect = OSError("disco cheio")

        # não levanta
        asyncio.run(AppInbox.deliver(runner, "msg", kind="feedback"))

        # mesmo com a central falhando, o push é tentado
        push.send.assert_called_once()
