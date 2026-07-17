from datetime import date, datetime

import pytest

from app.application.review.monthly_recap_builder import MonthlyRecapBuilder
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence import (
    personal_record_repository as repo_module,
)
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)
from tests.coach.factories import make_activity, make_runner

JULY = date(2026, 7, 1)


@pytest.fixture(autouse=True)
def _tmp_records_storage(tmp_path, monkeypatch):

    monkeypatch.setattr(repo_module, "_STORAGE", tmp_path / "records")


def _activity(day, month, distance_m, id_=1):

    return make_activity(
        id=id_,
        distance=distance_m,
        start_date=datetime(2026, month, day, 7, 0, 0),
    )


def test_month_with_no_activity_returns_none():

    runner = make_runner(weekly_training_days=3)

    history = TrainingHistory(activities=[_activity(15, 6, 10_000)])

    assert MonthlyRecapBuilder.build(runner, history, JULY) is None


def test_aggregates_km_and_runs_for_the_target_month():

    runner = make_runner(weekly_training_days=3)

    history = TrainingHistory(activities=[
        _activity(2, 7, 10_000, id_=1),
        _activity(10, 7, 8_000, id_=2),
        _activity(15, 6, 5_000, id_=3),  # mês anterior, fora
    ])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["total_km"] == 18.0
    assert recap["total_runs"] == 2
    assert recap["longest_km"] == 10.0
    assert recap["month_label"] == "Julho/2026"


def test_consistency_formula():
    """3x/semana esperado, julho tem 31 dias -> ~13 dias esperados
    (round(3*31/7) = 13). Treinou 6 dias distintos -> ~46%."""

    runner = make_runner(weekly_training_days=3)

    history = TrainingHistory(activities=[
        _activity(d, 7, 5_000, id_=d) for d in range(1, 7)
    ])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["consistency"] == round(6 / 13 * 100, 1)


def test_consistency_caps_at_100():

    runner = make_runner(weekly_training_days=1)

    history = TrainingHistory(activities=[
        _activity(d, 7, 5_000, id_=d) for d in range(1, 20)
    ])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["consistency"] == 100.0


def test_records_this_month_only_includes_dates_within_the_month():

    runner = make_runner(weekly_training_days=3, id="fulano")

    PersonalRecordRepository().save("fulano", {
        "seeded": True,
        "longest_km": 15.0,
        "longest_km_date": "2026-07-10",  # dentro de julho
        "pace_by_band": {"5-8": 5.0},
        "pace_by_band_dates": {"5-8": "2026-06-15"},  # fora (junho)
        "total_km_milestone": 100,
        "total_km_milestone_date": "2026-07-20",  # dentro
        "best_week_km": 30.0,
        "best_week_key": "2026-W27",  # início dessa semana cai em junho
    })

    history = TrainingHistory(activities=[_activity(1, 7, 5_000)])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    records = recap["records"]

    assert any("Corrida mais longa" in r for r in records)
    assert any("100 km" in r for r in records)
    assert not any("faixa" in r for r in records)  # pace PR é de junho
    assert not any("maior volume" in r for r in records)  # semana de junho


def test_no_records_file_means_empty_records_list():

    runner = make_runner(weekly_training_days=3, id="sem_recordes")

    history = TrainingHistory(activities=[_activity(1, 7, 5_000)])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["records"] == []
