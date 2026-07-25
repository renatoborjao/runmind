from datetime import datetime, time, timedelta

from app.core.clock import now_local
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
)


def _repo(tmp_path):

    repo = BodyReadingHistoryRepository()

    repo.storage = tmp_path

    return repo


def _snap(state, at) -> BodyReadingSnapshot:

    return BodyReadingSnapshot(
        at=at.isoformat(),
        body_state=state,
        limiter=None,
        acwr=1.0,
        acwr_status="OPTIMAL",
        hrv_recent=40.0,
        hrv_direction="stable",
        rhr_recent=55,
        rhr_direction="stable",
        sleep_avg_hours=7.0,
        short_nights=0,
        nights_counted=7,
    )


def test_load_missing_profile_is_empty(tmp_path):

    assert _repo(tmp_path).load("ninguem") == []


def test_record_and_load_roundtrip(tmp_path):

    repo = _repo(tmp_path)

    now = now_local()

    repo.record("renato", _snap("STRAINED", now - timedelta(days=1)))
    repo.record("renato", _snap("ABSORBING", now))

    stored = repo.load("renato")

    assert [s.body_state for s in stored] == ["STRAINED", "ABSORBING"]


def test_same_day_reading_collapses(tmp_path):

    repo = _repo(tmp_path)

    day = now_local().replace(hour=8)

    repo.record("renato", _snap("STRAINED", day))
    # releu no mesmo dia, mais tarde: substitui, não acumula
    repo.record("renato", _snap("ABSORBING", day.replace(hour=20)))

    stored = repo.load("renato")

    assert len(stored) == 1
    assert stored[0].body_state == "ABSORBING"


def test_cap_keeps_most_recent(tmp_path):

    repo = _repo(tmp_path)

    base = datetime.combine(now_local().date(), time(12, 0))

    # 30 dias distintos -> corta em _MAX (26), mantendo os mais recentes
    for i in range(30):

        repo.record("renato", _snap(f"S{i}", base - timedelta(days=30 - i)))

    stored = repo.load("renato")

    assert len(stored) == BodyReadingHistoryRepository._MAX
    assert stored[-1].body_state == "S29"
    assert stored[0].body_state == "S4"
