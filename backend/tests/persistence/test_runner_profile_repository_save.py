import json

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


def _isolated_repo(tmp_path):

    repo = RunnerProfileRepository()

    repo.storage = tmp_path

    return repo


def _profile_data(**overrides) -> dict:

    defaults = {
        "id": "fulano",
        "name": "Fulano",
        "age": 30,
        "weight": 70.0,
        "height": 1.75,
        "phone": "5511900000000",
        "goal": "10k",
        "weekly_training_days": 3,
        "notifications": True,  # chave que a entidade não conhece
    }

    defaults.update(overrides)

    return defaults


def test_save_creates_profile_loadable_by_entity(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("fulano", _profile_data())

    runner = repo.load("fulano")

    assert runner.name == "Fulano"
    assert repo.list_all() == ["fulano"]


def test_update_fields_merges_and_preserves_extra_keys(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("fulano", _profile_data())

    repo.update_fields(
        "fulano",
        {"strava_athlete_id": 777, "goal": "21k"},
    )

    data = json.loads(
        (tmp_path / "fulano.json").read_text(encoding="utf-8")
    )

    assert data["strava_athlete_id"] == 777
    assert data["goal"] == "21k"
    # inalterados e extras preservados
    assert data["name"] == "Fulano"
    assert data["notifications"] is True


def test_update_injuries_delegates_to_update_fields(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("fulano", _profile_data())

    repo.update_injuries("fulano", ["canelite"])

    data = json.loads(
        (tmp_path / "fulano.json").read_text(encoding="utf-8")
    )

    assert data["injuries"] == ["canelite"]
    assert data["notifications"] is True
