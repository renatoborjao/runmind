from app.infrastructure.persistence.workout_analysis_repository import (
    WorkoutAnalysisRepository,
)


def _isolated_repo(tmp_path):

    repo = WorkoutAnalysisRepository()

    repo.storage = tmp_path

    return repo


def test_find_missing_returns_none(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.find("desconhecido", "2026-09-19") is None


def test_record_and_find_by_date(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.record(
        "renato",
        activity_id=123,
        date="2026-09-19",
        distance_km=8.2,
        analysis="📊 Boa rodagem, ritmo controlado.",
        workout_type="Tempo",
    )

    hit = repo.find("renato", "2026-09-19")

    assert hit is not None
    assert hit["analysis"].startswith("📊 Boa rodagem")
    assert hit["workout_type"] == "Tempo"
    assert hit["distance_km"] == 8.2


def test_record_is_idempotent_by_activity_id(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.record("renato", 123, "2026-09-19", 8.2, "primeira", "Tempo")
    repo.record("renato", 123, "2026-09-19", 8.2, "corrigida", "Tempo")

    hit = repo.find("renato", "2026-09-19")

    assert hit["analysis"] == "corrigida"


def test_find_prefers_closest_distance_same_day(tmp_path):
    """Mesmo dia, dois treinos (raro, mas possível): casa pela distância mais
    próxima — reflete o dedup por data+distância do feed."""

    repo = _isolated_repo(tmp_path)

    repo.record("renato", 1, "2026-09-19", 5.0, "corrida curta", "Rodagem")
    repo.record("renato", 2, "2026-09-19", 12.0, "longão", "Longão")

    curta = repo.find("renato", "2026-09-19", distance_km=5.1)
    longo = repo.find("renato", "2026-09-19", distance_km=11.8)

    assert curta["analysis"] == "corrida curta"
    assert longo["analysis"] == "longão"


def test_find_falls_back_to_most_recent_when_distance_far(tmp_path):
    """Distância fora da tolerância (fontes divergem muito): não force um match
    errado por distância — devolve a mais recente do dia."""

    repo = _isolated_repo(tmp_path)

    repo.record("renato", 1, "2026-09-19", 5.0, "antiga", "Rodagem")
    repo.record("renato", 2, "2026-09-19", 5.0, "nova", "Rodagem")

    hit = repo.find("renato", "2026-09-19", distance_km=99.0)

    assert hit["analysis"] == "nova"
