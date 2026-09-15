from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.history.run_merge import merged_runs

MOD = "app.application.history.run_merge"


def _archive(*acts):
    return SimpleNamespace(load_activities=lambda _p: list(acts))


def _recorded(*runs):
    return SimpleNamespace(load=lambda _p: list(runs))


def _act(day, km, sport="run"):
    return SimpleNamespace(start_date=datetime(2026, 9, day), distance=km * 1000, sport=sport)


def test_app_run_counts_when_new():
    arch = _archive(_act(10, 10.0))
    rec = _recorded({"started_at": "2026-09-12T07:00:00", "distance_m": 5000})

    with (
        patch(f"{MOD}.ActivityArchiveRepository", lambda: arch),
        patch(f"{MOD}.RecordedRunRepository", lambda: rec),
    ):
        runs = merged_runs("p")

    assert len(runs) == 2
    total_km = round(sum(r.distance for r in runs) / 1000, 1)
    assert total_km == 15.0


def test_app_run_deduped_when_same_corrida():
    """Mesma corrida (data + distância ~igual) já arquivada não conta 2x."""

    arch = _archive(_act(10, 10.0))
    rec = _recorded({"started_at": "2026-09-10T07:00:00", "distance_m": 10050})  # ~10.05km

    with (
        patch(f"{MOD}.ActivityArchiveRepository", lambda: arch),
        patch(f"{MOD}.RecordedRunRepository", lambda: rec),
    ):
        runs = merged_runs("p")

    assert len(runs) == 1  # a do app foi deduplicada
    assert round(runs[0].distance / 1000, 1) == 10.0


def test_non_run_archive_is_excluded_but_app_run_counts():
    arch = _archive(_act(10, 30.0, sport="ride"))  # pedal não é corrida
    rec = _recorded({"started_at": "2026-09-11T07:00:00", "distance_m": 8000})

    with (
        patch(f"{MOD}.ActivityArchiveRepository", lambda: arch),
        patch(f"{MOD}.RecordedRunRepository", lambda: rec),
    ):
        runs = merged_runs("p")

    assert len(runs) == 1
    assert round(runs[0].distance / 1000, 1) == 8.0


def test_recorded_failure_is_safe():
    arch = _archive(_act(10, 10.0))

    class _Boom:
        def load(self, _p):
            raise OSError("disco")

    with (
        patch(f"{MOD}.ActivityArchiveRepository", lambda: arch),
        patch(f"{MOD}.RecordedRunRepository", _Boom),
    ):
        runs = merged_runs("p")  # não levanta

    assert len(runs) == 1
