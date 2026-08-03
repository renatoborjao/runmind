from datetime import datetime
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.progress_report import ProgressReport
from app.domain.entities.activity import Activity

MODULE = "app.application.coach.intelligence.progress_report"


def _run(y, m, d, speed, km=6.0) -> Activity:

    return Activity(
        id=int(f"{m}{d}"), name="run", sport="Run",
        start_date=datetime(y, m, d, 7, 0),
        timezone="America/Sao_Paulo",
        distance=km * 1000, moving_time=int(km * 1000 / speed),
        elapsed_time=int(km * 1000 / speed),
        average_speed=speed, max_speed=speed,
        average_heartrate=150.0, max_heartrate=170.0,
        elevation_gain=0.0, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None, raw={},
    )


def _stats():

    return {
        "first_date": "2026-05-01",
        "total_runs": 40,
        "total_km": 280.0,
        "longest_km": 15.0,
    }


def _patch_archive(activities, stats):

    repo = MagicMock()
    repo.load_activities.return_value = activities
    repo.stats.return_value = stats

    return patch(f"{MODULE}.ActivityArchiveRepository", return_value=repo)


def test_you_vs_you_shows_pace_gain_over_the_arc():
    """Corridas lentas há ~3 meses vs rápidas agora -> 'mais rápido no mesmo
    esforço' + a jornada de km."""

    activities = (
        [_run(2026, 5, d, 2.55) for d in (3, 8, 13, 18)]   # ~6:32/km (início)
        + [_run(2026, 8, d, 2.95) for d in (1, 4, 7, 10)]  # ~5:39/km (agora)
    )

    with _patch_archive(activities, _stats()):

        out = ProgressReport.build("renato")

    assert "você vs você" in out.lower()
    assert "MAIS RÁPIDO" in out
    assert "280 km" in out and "40 treinos" in out


def test_short_history_still_shows_journey_without_you_vs_you():
    """Sem arco de 8 semanas: sem a linha de VDOT, mas a jornada de km entra."""

    activities = [_run(2026, 8, d, 2.8) for d in (1, 3, 5, 7)]

    with _patch_archive(activities, _stats()):

        out = ProgressReport.build("renato")

    assert "MAIS RÁPIDO" not in out
    assert "280 km" in out


def test_none_without_enough_runs():

    with _patch_archive([_run(2026, 8, 1, 2.8)], None):

        assert ProgressReport.build("renato") is None
