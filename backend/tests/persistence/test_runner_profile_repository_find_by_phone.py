import json

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

_BASE_PROFILE = dict(
    id="runner-1",
    name="Renato",
    age=30,
    weight=70.0,
    height=175.0,
    phone="+5511975658679",
    goal="10k",
    weekly_training_days=4,
)


def _write_profile(tmp_path, filename, **overrides):

    data = {**_BASE_PROFILE, **overrides}

    (tmp_path / filename).write_text(
        json.dumps(data),
        encoding="utf-8",
    )


def _isolated_repo(tmp_path):

    repo = RunnerProfileRepository()

    repo.storage = tmp_path

    return repo


def test_finds_profile_by_normalized_phone(tmp_path):

    _write_profile(tmp_path, "renato.json")
    _write_profile(
        tmp_path,
        "camila.json",
        name="Camila",
        phone="+5511988887777",
    )

    repo = _isolated_repo(tmp_path)

    assert repo.find_by_phone("5511975658679@s.whatsapp.net") == "renato"
    assert repo.find_by_phone("5511988887777@s.whatsapp.net") == "camila"


def test_skips_invalid_json_files_without_crashing(tmp_path):

    _write_profile(tmp_path, "renato.json")

    (tmp_path / "renato_tokens.json").write_text(
        json.dumps({"access_token": "abc", "refresh_token": "def"}),
        encoding="utf-8",
    )

    repo = _isolated_repo(tmp_path)

    assert repo.find_by_phone("5511975658679@s.whatsapp.net") == "renato"


def test_returns_none_when_no_profile_matches(tmp_path):

    _write_profile(tmp_path, "renato.json")

    repo = _isolated_repo(tmp_path)

    assert repo.find_by_phone("5599999999999@s.whatsapp.net") is None


def test_list_all_returns_every_valid_profile(tmp_path):

    _write_profile(tmp_path, "renato.json")
    _write_profile(tmp_path, "camila.json", name="Camila")

    repo = _isolated_repo(tmp_path)

    assert sorted(repo.list_all()) == ["camila", "renato"]


def test_list_all_skips_invalid_json_files(tmp_path):

    _write_profile(tmp_path, "renato.json")

    (tmp_path / "renato_tokens.json").write_text(
        json.dumps({"access_token": "abc", "refresh_token": "def"}),
        encoding="utf-8",
    )

    repo = _isolated_repo(tmp_path)

    assert repo.list_all() == ["renato"]
