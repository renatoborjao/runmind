from app.domain.entities.memory_entry import MemoryEntry
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)


def _isolated_repo(tmp_path):

    repo = RunnerMemoryRepository()

    repo.storage = tmp_path

    return repo


def _entry(entry_id: str, category: str = "lesao", **overrides) -> MemoryEntry:

    defaults = dict(
        id=entry_id,
        category=category,
        content="Dor no joelho direito",
        source="conversation",
        created_at="2026-07-03T10:00:00+00:00",
        status="active",
    )

    defaults.update(overrides)

    return MemoryEntry(**defaults)


def test_load_returns_empty_list_when_no_file(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.load("renato") == []


def test_add_persists_entry(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.add("renato", _entry("m-1"))

    entries = repo.load("renato")

    assert len(entries) == 1
    assert entries[0].id == "m-1"
    assert entries[0].category == "lesao"
    assert entries[0].status == "active"


def test_archive_marks_entries_and_active_filters_them(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.add("renato", _entry("m-1"))
    repo.add("renato", _entry("m-2", category="disponibilidade",
                              content="Viaja semana que vem"))

    repo.archive("renato", ["m-1"])

    entries = repo.load("renato")
    assert len(entries) == 2

    active = repo.active("renato")
    assert [entry.id for entry in active] == ["m-2"]

    archived = [e for e in entries if e.status == "archived"]
    assert [entry.id for entry in archived] == ["m-1"]


def test_archive_with_empty_ids_is_noop(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.add("renato", _entry("m-1"))

    repo.archive("renato", [])

    assert repo.active("renato")[0].id == "m-1"
