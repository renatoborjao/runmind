from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry
from app.infrastructure.persistence.readiness_diary_repository import (
    ReadinessDiaryRepository,
)


def _repo(tmp_path):

    repo = ReadinessDiaryRepository()
    repo.storage = tmp_path
    return repo


def _entry(day, tier="BRAKE", would_notify=True, from_tier=None):

    return ReadinessDiaryEntry(
        day=day,
        at=f"{day}T09:00:00-03:00",
        tier=tier,
        body_state="STRAINED",
        reason="corpo sobrecarregado; limitador: sono",
        demand="demanding",
        would_notify=would_notify,
        from_tier=from_tier,
    )


def test_missing_profile_is_empty(tmp_path):

    repo = _repo(tmp_path)

    assert repo.load("ninguem") == []
    assert repo.last("ninguem") is None


def test_record_and_load_roundtrip(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato2", _entry("2026-07-24", tier="NEUTRAL"))
    repo.record("renato2", _entry("2026-07-25", tier="BRAKE"))

    stored = repo.load("renato2")

    assert [e.day for e in stored] == ["2026-07-24", "2026-07-25"]
    assert repo.last("renato2").tier == "BRAKE"


def test_mesmo_dia_substitui(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato2", _entry("2026-07-25", tier="CAUTION"))
    # reavaliação pós-treino no MESMO dia atualiza, não duplica
    repo.record("renato2", _entry("2026-07-25", tier="BRAKE"))

    stored = repo.load("renato2")

    assert len(stored) == 1
    assert stored[0].tier == "BRAKE"


def test_teto_de_registros(tmp_path):

    repo = _repo(tmp_path)

    for d in range(1, 70):

        repo.record("renato2", _entry(f"2026-05-{d:02d}" if d <= 31
                                       else f"2026-06-{d - 31:02d}"))

    assert len(repo.load("renato2")) <= 60
