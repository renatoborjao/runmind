"""Prova registrada pela conversa não herda o tempo-alvo da prova anterior."""

from datetime import date
from unittest.mock import MagicMock, patch

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)

MODULE = "app.application.coach.memory.runner_memory_service"


def _sync(current, race):

    repo = MagicMock()
    repo.load.return_value = current

    with (
        patch(f"{MODULE}.RunnerProfileRepository", return_value=repo),
        patch(
            "app.infrastructure.persistence.race_repository.RaceRepository"
        ),
    ):

        RunnerMemoryService._sync_race("mauricio", race)

    return repo.update_fields.call_args.args[1]


def test_new_race_without_target_clears_the_inherited_time():
    """Maurício 27/09: a 15k (pace 5:30) herdou os 57:00 da 10k — o plano
    recebia 'ritmo-alvo ~3:48/km' nos 15 km."""

    current = MagicMock(
        race_date=date(2026, 9, 19), target_race="10 km", target_time="00:57:00",
    )

    updates = _sync(current, {"date": "2026-12-20", "name": "15 km"})

    assert updates["race_date"] == "2026-12-20"
    assert updates["target_race"] == "15 km"
    assert updates["target_time"] is None


def test_same_race_mentioned_again_keeps_its_time():

    current = MagicMock(
        race_date=date(2026, 12, 20), target_race="15 km", target_time="01:22:30",
    )

    updates = _sync(current, {"date": "2026-12-20", "name": "15 km"})

    assert "target_time" not in updates


def test_new_race_with_target_sets_it():

    current = MagicMock(
        race_date=date(2026, 9, 19), target_race="10 km", target_time="00:57:00",
    )

    updates = _sync(
        current,
        {"date": "2026-12-20", "name": "15 km", "target_time": "01:22:30"},
    )

    assert updates["target_time"] == "01:22:30"
