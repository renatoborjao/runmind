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


def test_remove_deletes_only_the_given_activity(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.upsert_many("renato", [
        make_activity(id=1, distance=10000.0),
        make_activity(id=2, distance=8000.0),
    ])

    assert repo.remove("renato", 1) is True

    records = repo.load("renato")

    assert [r["id"] for r in records] == [2]


def test_remove_unknown_activity_is_noop(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.upsert_many("renato", [make_activity(id=1)])

    assert repo.remove("renato", 999) is False

    assert len(repo.load("renato")) == 1


def test_remove_from_empty_archive_is_noop(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.remove("renato", 1) is False


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


def test_load_activities_dedups_garmin_strava_twins(tmp_path):
    """Mesma corrida do Garmin (com zonas) e do Strava (sem), ids diferentes,
    mesma data/distância/tempo -> load_activities colapsa numa só, preferindo a
    com zonas de FC."""

    from datetime import datetime

    repo = _isolated_repo(tmp_path)

    day = datetime(2026, 7, 25, 6, 0, 0)

    strava = make_activity(
        id=19000, distance=14030.0, moving_time=5400,
        start_date=day, hr_zone_minutes=None,
    )

    garmin = make_activity(
        id=23000, distance=14030.0, moving_time=5400,
        start_date=day, hr_zone_minutes=[0, 0, 10, 70, 10],
    )

    repo.upsert_many("renato", [strava, garmin])

    activities = repo.load_activities("renato")

    assert len(activities) == 1
    assert activities[0].hr_zone_minutes == [0, 0, 10, 70, 10]  # a cópia rica


def test_dedup_merges_temp_from_strava_onto_garmin_copy(tmp_path):
    """A cópia Garmin (com zonas) é mantida, mas HERDA a temperatura que só a
    cópia Strava trouxe — pra a normalização de calor do EF funcionar mesmo em
    atleta analisado via Garmin."""

    from datetime import datetime

    repo = _isolated_repo(tmp_path)

    day = datetime(2026, 7, 25, 6, 0, 0)

    strava = make_activity(
        id=19000, distance=14030.0, moving_time=5400,
        start_date=day, hr_zone_minutes=None, air_temp_c=24.0,
    )

    garmin = make_activity(
        id=23000, distance=14030.0, moving_time=5400,
        start_date=day, hr_zone_minutes=[0, 0, 10, 70, 10], air_temp_c=None,
    )

    repo.upsert_many("renato", [strava, garmin])

    activities = repo.load_activities("renato")

    assert len(activities) == 1
    assert activities[0].hr_zone_minutes == [0, 0, 10, 70, 10]  # a cópia rica
    assert activities[0].air_temp_c == 24.0                      # temp herdada


def test_temp_survives_save_and_reload(tmp_path):
    """air_temp_c é persistido e relido (não some no round-trip do arquivo)."""

    repo = _isolated_repo(tmp_path)

    repo.upsert_many("renato", [make_activity(id=1, air_temp_c=27.0)])

    reloaded = repo.load_activities("renato")

    assert reloaded[0].air_temp_c == 27.0


def test_load_activities_keeps_distinct_runs(tmp_path):
    """Corridas de dias diferentes não são colapsadas."""

    from datetime import datetime

    repo = _isolated_repo(tmp_path)

    a = make_activity(id=1, distance=10000.0, start_date=datetime(2026, 7, 1, 7, 0))
    b = make_activity(id=2, distance=10000.0, start_date=datetime(2026, 7, 3, 7, 0))

    repo.upsert_many("renato", [a, b])

    assert len(repo.load_activities("renato")) == 2
