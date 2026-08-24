from app.infrastructure.persistence.race_result_repository import (
    RaceResultRepository,
)


def _repo(tmp_path):
    repo = RaceResultRepository()
    repo.storage = tmp_path
    return repo


def test_record_and_load(tmp_path):
    repo = _repo(tmp_path)

    assert repo.load("renato2") == []

    repo.record("renato2", {"date": "2026-08-23", "race_label": "10 km"})

    results = repo.load("renato2")
    assert len(results) == 1
    assert results[0]["date"] == "2026-08-23"


def test_record_is_idempotent_by_date(tmp_path):
    """Reprocessar a mesma prova não duplica — substitui pela data."""

    repo = _repo(tmp_path)

    repo.record("renato2", {"date": "2026-08-23", "time": "54:20"})
    repo.record("renato2", {"date": "2026-08-23", "time": "54:18"})
    repo.record("renato2", {"date": "2026-07-01", "time": "25:00"})

    results = repo.load("renato2")
    assert len(results) == 2
    latest = next(r for r in results if r["date"] == "2026-08-23")
    assert latest["time"] == "54:18"


def test_load_survives_corrupt_file(tmp_path):
    repo = _repo(tmp_path)
    (tmp_path / "renato2.json").write_text("lixo{", encoding="utf-8")

    assert repo.load("renato2") == []
