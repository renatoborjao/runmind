from datetime import datetime

from app.infrastructure.persistence.cross_training_repository import (
    CrossTrainingRepository,
)
from tests.coach.factories import make_activity


def _isolated_repo(tmp_path):

    repo = CrossTrainingRepository()

    repo.storage = tmp_path

    return repo


def test_upsert_is_idempotent_by_id(tmp_path):

    repo = _isolated_repo(tmp_path)

    strength = make_activity(id=1, sport="strength_training")

    repo.upsert_many("mauricio", [strength])
    repo.upsert_many("mauricio", [strength])

    assert len(repo.load("mauricio")) == 1


def test_roundtrip_keeps_load_fields_and_zeroes_running(tmp_path):

    repo = _isolated_repo(tmp_path)

    swim = make_activity(
        id=7,
        sport="lap_swimming",
        moving_time=2400,
        average_heartrate=138.0,
        start_date=datetime(2026, 7, 20, 6, 0, 0),
    )

    repo.upsert_many("fernanda", [swim])

    (activity,) = repo.load_activities("fernanda")

    # o que a carga precisa é preservado
    assert activity.sport == "lap_swimming"
    assert activity.moving_time == 2400
    assert activity.average_heartrate == 138.0

    # nada de corrida vaza (distância zerada — não é treino de corrida)
    assert activity.distance == 0.0


def test_only_minimal_fields_persisted(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.upsert_many(
        "mauricio", [make_activity(id=3, sport="strength_training")]
    )

    (record,) = repo.load("mauricio")

    assert set(record) == {
        "id", "sport", "start_date", "moving_time", "average_heartrate"
    }
