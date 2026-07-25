from datetime import date, datetime, time
from unittest.mock import patch

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_FIRST,
    TRAJ_IMPROVED,
)
from app.domain.entities.training_load import TrainingLoad
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
)

MOD = "app.application.coach.intelligence.body_reading_service"


def _reading(state=BODY_STRAINED, has_data=True) -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=400.0, acwr=1.25,
            status="OPTIMAL", days_of_history=28,
        ),
        recovery=RecoveryTrend(
            hrv_recent=40.0, hrv_direction="falling",
            rhr_recent=58, rhr_direction="falling",
            sleep_avg_hours=6.0, short_nights=4, nights_counted=13,
            days_covered=14 if has_data else 0,
        ),
        body_state=state,
        limiter="sono" if has_data else None,
    )


def _run(tmp_path, reading, day: date, persist=True):
    """Roda o service com o builder mockado e o repo apontado pro tmp."""

    repo = BodyReadingHistoryRepository()

    repo.storage = tmp_path

    at = datetime.combine(day, time(20, 0))

    with patch(f"{MOD}.BodyReadingBuilder.build", return_value=reading), patch(
        f"{MOD}.BodyReadingHistoryRepository", lambda: repo
    ), patch(f"{MOD}.today_local", return_value=day), patch(
        f"{MOD}.now_local", return_value=at
    ):

        return BodyReadingService.read("renato", persist=persist), repo


def test_first_read_persists_and_reports_first(tmp_path):

    (reading, traj), repo = _run(tmp_path, _reading(), date(2026, 7, 13))

    assert traj.movement == TRAJ_FIRST
    assert len(repo.load("renato")) == 1
    assert repo.load("renato")[0].body_state == BODY_STRAINED


def test_second_read_sees_trajectory(tmp_path):

    _run(tmp_path, _reading(BODY_STRAINED), date(2026, 7, 13))

    (reading, traj), repo = _run(
        tmp_path, _reading(BODY_ABSORBING), date(2026, 7, 20)
    )

    # saiu do alerta desde a leitura anterior
    assert traj.movement == TRAJ_IMPROVED
    assert traj.previous_state == BODY_STRAINED
    assert len(repo.load("renato")) == 2


def test_persist_false_never_writes(tmp_path):

    (_, traj), repo = _run(
        tmp_path, _reading(), date(2026, 7, 13), persist=False
    )

    assert repo.load("renato") == []


def test_no_recovery_data_is_not_persisted(tmp_path):

    (_, traj), repo = _run(
        tmp_path, _reading(has_data=False), date(2026, 7, 13)
    )

    # leitura sem corpo não vira snapshot (não ajuda a comparar nada)
    assert repo.load("renato") == []
