import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.race_debrief import RaceDebrief
from tests.coach.factories import make_runner

MODULE = "app.application.coach.intelligence.race_debrief"

RACE_DAY = date(2026, 8, 23)


def _runner(target_time="00:50:00", race_date="2026-08-23"):
    return make_runner(
        target_race="10 km", target_time=target_time, race_date=race_date,
    )


def _activity(distance_m=10000.0, moving_sec=2940, day=RACE_DAY):
    """enriched.activity com os campos que o debrief lê."""
    return SimpleNamespace(
        activity=SimpleNamespace(
            distance=distance_m,
            moving_time=moving_sec,
            start_date=datetime(day.year, day.month, day.day, 8, 0),
        )
    )


def _run(runner, enriched):
    with patch(f"{MODULE}.RunnerProfileRepository") as repo_cls:
        repo = MagicMock()
        repo_cls.return_value = repo
        reply = asyncio.run(
            RaceDebrief.after_feedback("renato2", runner, enriched)
        )
        return reply, repo


def test_beat_target_celebrates_and_clears_race_date():

    # 48:00 < meta 50:00
    reply, repo = _run(_runner(), _activity(moving_sec=2880))

    assert reply is not None
    assert "BATEU" in reply or "CONSEGUIU" in reply
    assert "48:00" in reply
    # consumiu a prova
    repo.update_fields.assert_called_once_with("renato2", {"race_date": None})


def test_near_miss_is_encouraging():

    # 50:30 -> dentro de 2% de 50:00
    reply, _ = _run(_runner(), _activity(moving_sec=3030))

    assert reply is not None
    assert "pertíssimo" in reply


def test_missed_target_is_honest():

    # 55:00 > meta 50:00 (fora da margem)
    reply, _ = _run(_runner(), _activity(moving_sec=3300))

    assert reply is not None
    assert "não saiu" in reply.lower()


def test_not_the_race_when_distance_off():

    # 5 km num dia de prova de 10 km -> não é a prova
    reply, repo = _run(_runner(), _activity(distance_m=5000.0))

    assert reply is None
    repo.update_fields.assert_not_called()


def test_no_race_date_returns_none():

    reply, repo = _run(_runner(race_date=None), _activity())

    assert reply is None
    repo.update_fields.assert_not_called()


def test_finish_without_target_still_celebrates():

    reply, repo = _run(_runner(target_time=None), _activity())

    assert reply is not None
    assert "CRUZOU" in reply
    repo.update_fields.assert_called_once()
