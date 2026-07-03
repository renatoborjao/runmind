import json

import pytest

from app.application.use_cases.owner_resolver import OwnerResolver
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MODULE = "app.application.use_cases.owner_resolver"


def _write_profile(directory, name: str, athlete_id: int | None):

    data = {
        "id": name,
        "name": name.capitalize(),
        "age": 30,
        "weight": 70.0,
        "height": 1.75,
        "phone": f"+55119{athlete_id or 0:08d}",
        "goal": "10k",
        "weekly_training_days": 3,
        "strava_athlete_id": athlete_id,
    }

    (directory / f"{name}.json").write_text(
        json.dumps(data),
        encoding="utf-8",
    )


def _isolated_repo(tmp_path):

    repo = RunnerProfileRepository()

    repo.storage = tmp_path

    return repo


def test_resolves_profile_by_strava_athlete_id(tmp_path, monkeypatch):

    repo = _isolated_repo(tmp_path)

    _write_profile(tmp_path, "renato", 111)
    _write_profile(tmp_path, "fulano", 222)

    monkeypatch.setattr(
        f"{MODULE}.RunnerProfileRepository",
        lambda: repo,
    )

    assert OwnerResolver.resolve(222) == "fulano"


def test_invalid_file_does_not_break_resolution(tmp_path, monkeypatch):

    repo = _isolated_repo(tmp_path)

    # arquivo que não é um perfil (ex: tokens) no meio do diretório
    (tmp_path / "aaa_tokens.json").write_text(
        json.dumps({"access_token": "x"}),
        encoding="utf-8",
    )

    _write_profile(tmp_path, "renato", 111)

    monkeypatch.setattr(
        f"{MODULE}.RunnerProfileRepository",
        lambda: repo,
    )

    assert OwnerResolver.resolve(111) == "renato"


def test_raises_when_owner_unknown(tmp_path, monkeypatch):

    repo = _isolated_repo(tmp_path)

    _write_profile(tmp_path, "renato", 111)

    monkeypatch.setattr(
        f"{MODULE}.RunnerProfileRepository",
        lambda: repo,
    )

    with pytest.raises(Exception, match="owner_id=999"):

        OwnerResolver.resolve(999)
