import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from tests.coach.factories import make_runner

MODULE = "app.application.review.weekly_review_notifier"


def _run_notify_all(profiles, runners, messages):

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.WeeklyReviewBuilder"),
        patch(f"{MODULE}.WeeklyReviewNarrativeWriter") as mock_narrative,
        patch(f"{MODULE}.WeeklyReviewMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.CoachOutbox") as mock_notification,
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 12, 19, 0)),
        patch(f"{MODULE}.DispatchGuard") as mock_guard,
        patch(f"{MODULE}.StatePortraitService") as mock_portrait_service,
        patch(f"{MODULE}.StatePortraitWriter") as mock_portrait_writer,
    ):

        mock_guard.already_sent.return_value = False

        # por padrão, o retrato não tem nada a dizer -> não é enviado, então os
        # testes do RESUMO isolam só o resumo
        mock_portrait_service.read.return_value = (MagicMock(), MagicMock())

        mock_portrait_writer.write.return_value = None

        mock_narrative.write = AsyncMock(return_value=None)

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = profiles
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.side_effect = runners

        mock_load_history.execute = AsyncMock(return_value=object())

        mock_formatter.format.side_effect = messages

        mock_notification.send = AsyncMock()

        asyncio.run(WeeklyReviewNotifier.notify_all())

        return mock_notification


def test_notify_all_sends_review_to_every_profile():

    mock_notification = _run_notify_all(
        profiles=["renato", "camila"],
        runners=[
            make_runner(name="Renato", phone="+5511900000001"),
            make_runner(name="Camila", phone="+5511900000002"),
        ],
        messages=["resumo renato", "resumo camila"],
    )

    assert mock_notification.send.await_count == 2

    sent = [call.args for call in mock_notification.send.await_args_list]
    names_msgs = [(r.name, msg) for r, msg in sent]
    # o resumo agora leva o rodapé "💡 Você sabia?" colado (descoberta)
    assert any(
        name == "Renato" and msg.startswith("resumo renato") and "💡" in msg
        for name, msg in names_msgs
    )


def test_does_not_send_when_formatter_returns_none():

    mock_notification = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato", phone="+5511900000001")],
        messages=[None],
    )

    mock_notification.send.assert_not_awaited()


def test_notify_all_continues_after_one_profile_fails():

    mock_notification = _run_notify_all(
        profiles=["quebrado", "renato"],
        runners=[
            Exception("perfil corrompido"),
            make_runner(name="Renato", phone="+5511900000001"),
        ],
        messages=["resumo renato"],
    )

    mock_notification.send.assert_awaited_once()
    runner, msg = mock_notification.send.await_args.args
    assert runner.name == "Renato"
    assert msg.startswith("resumo renato")


# ---------------- retrato "como você está" pós-resumo ----------------


def _run_send_state_portrait(message):

    runner = make_runner(name="Renato", phone="+5511900000001")

    with (
        patch(f"{MODULE}.StatePortraitService") as mock_service,
        patch(f"{MODULE}.StatePortraitWriter") as mock_writer,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
    ):

        mock_service.read.return_value = (MagicMock(), MagicMock())

        mock_writer.write.return_value = message

        mock_outbox.send = AsyncMock()

        asyncio.run(
            WeeklyReviewNotifier._send_state_portrait("renato", runner)
        )

        return mock_outbox


def test_state_portrait_sent_when_there_is_a_reading():

    mock_outbox = _run_send_state_portrait("📷 Como você está, Renato...")

    mock_outbox.send.assert_awaited_once()

    _, msg = mock_outbox.send.await_args.args
    assert msg.startswith("📷 Como você está")


def test_state_portrait_skipped_when_nothing_to_say():

    mock_outbox = _run_send_state_portrait(None)

    mock_outbox.send.assert_not_awaited()
