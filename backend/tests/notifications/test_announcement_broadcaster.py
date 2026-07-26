import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.notifications.announcement_broadcaster import (
    AnnouncementBroadcaster,
)

MODULE = "app.application.notifications.announcement_broadcaster"


def _run(announcement_id="2026-07-novidades", message="Novidades!", **kwargs):

    already_sent = kwargs.pop("already_sent", set())

    profiles = kwargs.pop("profiles", ["renato", "fernanda", "mauricio"])

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.DispatchGuard") as mock_guard,
    ):

        mock_repo_cls.return_value.list_all.return_value = profiles

        mock_load.execute.side_effect = lambda p: SimpleNamespace(
            name=p.capitalize()
        )

        mock_guard.already_sent.side_effect = (
            lambda kind, profile, period: profile in already_sent
        )

        mock_outbox.send = AsyncMock()

        result = asyncio.run(
            AnnouncementBroadcaster.broadcast(
                announcement_id, message, **kwargs
            )
        )

        return result, mock_outbox, mock_guard


def test_broadcasts_to_all_active_and_marks_each():

    result, outbox, guard = _run()

    assert result["sent"] == ["renato", "fernanda", "mauricio"]
    assert outbox.send.await_count == 3
    assert guard.mark.call_count == 3     # marca cada um (dedup futuro)


def test_dedup_skips_already_sent():
    """Rodar de novo não reenvia pra quem já recebeu este informativo."""

    result, outbox, _ = _run(already_sent={"renato"})

    assert result["skipped"] == ["renato"]
    assert result["sent"] == ["fernanda", "mauricio"]
    assert outbox.send.await_count == 2


def test_one_failure_does_not_block_the_rest():

    _, outbox, _ = _run()  # baseline

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.DispatchGuard") as mock_guard,
    ):

        mock_repo_cls.return_value.list_all.return_value = ["a", "b", "c"]

        mock_load.execute.side_effect = lambda p: SimpleNamespace(name=p)

        mock_guard.already_sent.return_value = False

        async def send(runner, msg):

            if runner.name == "b":

                raise RuntimeError("canal fora do ar")

        mock_outbox.send = AsyncMock(side_effect=send)

        result = asyncio.run(
            AnnouncementBroadcaster.broadcast("id", "oi")
        )

    assert result["sent"] == ["a", "c"]
    assert [p for p, _ in result["failed"]] == ["b"]


def test_dry_run_sends_nothing_but_previews():

    result, outbox, guard = _run(dry_run=True)

    outbox.send.assert_not_awaited()
    guard.mark.assert_not_called()
    assert set(result["preview"]) == {"renato", "fernanda", "mauricio"}


def test_personalizes_name_placeholder():

    result, _, _ = _run(
        message="Olá, {name}! Novidades no RunMind.",
        dry_run=True,
    )

    assert result["preview"]["renato"] == "Olá, Renato! Novidades no RunMind."


def test_only_restricts_to_given_profiles():
    """Permite testar num atleta antes de mandar pra todos."""

    result, outbox, _ = _run(only=["renato"])

    assert result["sent"] == ["renato"]
    assert outbox.send.await_count == 1
