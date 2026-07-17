import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.review.monthly_recap_notifier import MonthlyRecapNotifier
from tests.coach.factories import make_runner

MODULE = "app.application.review.monthly_recap_notifier"


def _run_notify_all(
    profiles,
    runners,
    recaps,
    messages=None,
    now=datetime(2026, 7, 1, 9, 0),
    already_sent=False,
):

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.MonthlyRecapBuilder") as mock_builder,
        patch(f"{MODULE}.MonthlyRecapNarrativeWriter") as mock_narrative,
        patch(f"{MODULE}.MonthlyRecapMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.now_in", return_value=now),
        patch(f"{MODULE}.DispatchGuard") as mock_guard,
    ):

        mock_guard.already_sent.return_value = already_sent

        mock_narrative.write = AsyncMock(return_value=None)

        mock_repo = MagicMock()
        mock_repo.list_all.return_value = profiles
        mock_repo_cls.return_value = mock_repo

        mock_load_runner.execute.side_effect = runners

        mock_load_history.execute = AsyncMock(return_value=object())

        mock_builder.build.side_effect = recaps

        if messages is not None:

            mock_formatter.format.side_effect = messages

        mock_outbox.send = AsyncMock()

        asyncio.run(MonthlyRecapNotifier.notify_all())

        return mock_outbox, mock_guard


def test_sends_recap_on_day_one_at_nine_local():

    mock_outbox, mock_guard = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato")],
        recaps=[{"month_label": "Junho/2026"}],
        messages=["recap renato"],
    )

    mock_outbox.send.assert_awaited_once()
    runner, msg = mock_outbox.send.await_args.args
    assert runner.name == "Renato"
    assert msg == "recap renato"

    # o mês recapitulado é o ANTERIOR ao dia 1 corrente (julho -> junho)
    mock_guard.mark.assert_called_once_with(
        "monthly_recap", "renato", "2026-06",
    )


def test_does_not_send_outside_day_one_nine_am():

    mock_outbox, _ = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato")],
        recaps=[],
        now=datetime(2026, 7, 1, 10, 0),  # 10h, não 9h
    )

    mock_outbox.send.assert_not_awaited()


def test_does_not_send_on_a_day_other_than_one():

    mock_outbox, _ = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato")],
        recaps=[],
        now=datetime(2026, 7, 15, 9, 0),
    )

    mock_outbox.send.assert_not_awaited()


def test_dedup_skips_already_sent_month():

    mock_outbox, _ = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato")],
        recaps=[],
        already_sent=True,
    )

    mock_outbox.send.assert_not_awaited()


def test_no_activity_in_the_month_sends_nothing():
    """Builder retorna None (mês sem treino) -> nenhuma mensagem."""

    mock_outbox, _ = _run_notify_all(
        profiles=["renato"],
        runners=[make_runner(name="Renato")],
        recaps=[None],
    )

    mock_outbox.send.assert_not_awaited()


def test_notify_all_continues_after_one_profile_fails():

    mock_outbox, _ = _run_notify_all(
        profiles=["quebrado", "renato"],
        runners=[
            Exception("perfil corrompido"),
            make_runner(name="Renato"),
        ],
        recaps=[{"month_label": "Junho/2026"}],
        messages=["recap renato"],
    )

    mock_outbox.send.assert_awaited_once()
    runner, msg = mock_outbox.send.await_args.args
    assert runner.name == "Renato"
