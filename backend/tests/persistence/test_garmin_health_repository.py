from app.domain.entities.daily_health import DailyHealth
from app.infrastructure.persistence import (
    garmin_health_repository as repo_module,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)


def _isolate(tmp_path):

    repo_module._STORAGE = tmp_path / "garmin_health"


def test_upsert_and_load(tmp_path):

    _isolate(tmp_path)

    repo = GarminHealthRepository()

    repo.upsert("renato2", DailyHealth(date="2026-07-20", sleep_score=70))

    loaded = repo.load("renato2")

    assert len(loaded) == 1
    assert loaded[0].sleep_score == 70


def test_upsert_same_date_replaces_not_duplicates(tmp_path):

    _isolate(tmp_path)

    repo = GarminHealthRepository()

    repo.upsert("renato2", DailyHealth(date="2026-07-20", sleep_score=70))

    repo.upsert("renato2", DailyHealth(date="2026-07-20", sleep_score=85))

    loaded = repo.load("renato2")

    assert len(loaded) == 1
    assert loaded[0].sleep_score == 85


def test_kept_ordered_by_date(tmp_path):

    _isolate(tmp_path)

    repo = GarminHealthRepository()

    repo.upsert("renato2", DailyHealth(date="2026-07-21"))

    repo.upsert("renato2", DailyHealth(date="2026-07-19"))

    repo.upsert("renato2", DailyHealth(date="2026-07-20"))

    dates = [h.date for h in repo.load("renato2")]

    assert dates == ["2026-07-19", "2026-07-20", "2026-07-21"]


def test_has_date(tmp_path):

    _isolate(tmp_path)

    repo = GarminHealthRepository()

    repo.upsert("renato2", DailyHealth(date="2026-07-20"))

    assert repo.has_date("renato2", "2026-07-20") is True
    assert repo.has_date("renato2", "2026-07-21") is False


def test_latest_and_profiles_are_independent(tmp_path):

    _isolate(tmp_path)

    repo = GarminHealthRepository()

    repo.upsert("renato2", DailyHealth(date="2026-07-19", sleep_score=1))

    repo.upsert("renato2", DailyHealth(date="2026-07-21", sleep_score=9))

    assert repo.latest("renato2").sleep_score == 9

    # outro atleta é independente e começa vazio
    assert repo.load("fernanda") == []
    assert repo.latest("fernanda") is None
