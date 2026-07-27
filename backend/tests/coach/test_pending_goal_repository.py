import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from app.core.clock import now_local
from app.infrastructure.persistence.pending_goal_repository import (
    PENDING_TTL_MINUTES,
    PendingGoalRepository,
)

MODULE = "app.infrastructure.persistence.pending_goal_repository"


def _repo(tmp: str) -> PendingGoalRepository:

    repo = PendingGoalRepository()
    repo.storage = Path(tmp)
    return repo


def test_mark_then_is_pending():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        assert repo.is_pending("renato") is False

        repo.mark("renato")

        assert repo.is_pending("renato") is True


def test_clear_removes_state():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        repo.mark("renato")
        repo.clear("renato")

        assert repo.is_pending("renato") is False


def test_expires_after_ttl_and_cleans_file():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        repo.mark("renato")

        future = now_local() + timedelta(minutes=PENDING_TTL_MINUTES + 1)

        with patch(f"{MODULE}.now_local", return_value=future):

            assert repo.is_pending("renato") is False

        assert not (repo.storage / "renato.json").exists()


def test_corrupt_file_is_cleared():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        (repo.storage / "renato.json").write_text(
            "lixo não-json", encoding="utf-8"
        )

        assert repo.is_pending("renato") is False


def test_isolated_per_profile():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        repo.mark("renato")

        assert repo.is_pending("fernanda") is False
        assert repo.is_pending("renato") is True
