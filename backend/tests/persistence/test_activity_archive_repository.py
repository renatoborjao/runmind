from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from tests.coach.factories import make_activity


def _isolated_repo(tmp_path):

    repo = ActivityArchiveRepository()

    repo.storage = tmp_path

    return repo


def test_upsert_is_idempotent_by_id(tmp_path):

    repo = _isolated_repo(tmp_path)

    activity = make_activity(id=1, distance=10000.0)

    repo.upsert_many("renato", [activity])
    repo.upsert_many("renato", [activity])

    assert len(repo.load("renato")) == 1


def test_upsert_updates_existing_and_sorts_by_date(tmp_path):

    from datetime import datetime

    repo = _isolated_repo(tmp_path)

    newer = make_activity(
        id=2,
        distance=8000.0,
        start_date=datetime(2026, 7, 2, 7, 0, 0),
    )

    older = make_activity(
        id=1,
        distance=5000.0,
        start_date=datetime(2026, 6, 1, 7, 0, 0),
    )

    repo.upsert_many("renato", [newer])
    repo.upsert_many("renato", [older])

    records = repo.load("renato")

    assert [r["id"] for r in records] == [1, 2]

    # atualização do mesmo id substitui o registro
    repo.upsert_many(
        "renato",
        [make_activity(id=1, distance=5500.0,
                       start_date=datetime(2026, 6, 1, 7, 0, 0))],
    )

    assert repo.load("renato")[0]["distance"] == 5500.0


def test_stats_aggregates_lifetime(tmp_path):

    from datetime import datetime

    repo = _isolated_repo(tmp_path)

    repo.upsert_many("renato", [
        make_activity(id=1, distance=10000.0,
                      start_date=datetime(2026, 3, 14, 7, 0, 0)),
        make_activity(id=2, distance=21100.0,
                      start_date=datetime(2026, 5, 1, 7, 0, 0)),
    ])

    stats = repo.stats("renato")

    assert stats == {
        "total_runs": 2,
        "total_km": 31.1,
        "first_date": "2026-03-14",
        "longest_km": 21.1,
    }


def test_stats_none_when_empty(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.stats("renato") is None
