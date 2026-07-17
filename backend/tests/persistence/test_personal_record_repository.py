from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)


def _isolated_repo(tmp_path):

    repo = PersonalRecordRepository()

    repo.storage = tmp_path

    return repo


def test_load_missing_profile_returns_empty_dict(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.load("desconhecido") == {}


def test_save_and_load_roundtrip(tmp_path):

    repo = _isolated_repo(tmp_path)

    data = {
        "seeded": True,
        "longest_km": 21.1,
        "total_km_milestone": 500,
        "best_week_km": 62.3,
        "best_week_key": "2026-W28",
        "pace_by_band": {"5-8": 5.12},
    }

    repo.save("mauricio", data)

    assert repo.load("mauricio") == data


def test_save_overwrites_previous_value(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("mauricio", {"seeded": True, "longest_km": 10.0})
    repo.save("mauricio", {"seeded": True, "longest_km": 15.0})

    assert repo.load("mauricio")["longest_km"] == 15.0


def test_corrupted_file_returns_empty_dict(tmp_path):

    repo = _isolated_repo(tmp_path)

    (tmp_path / "mauricio.json").write_text("{ not json", encoding="utf-8")

    assert repo.load("mauricio") == {}
