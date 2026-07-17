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


def _run(day, month, distance_m, speed, id_=1):

    return make_activity(
        id=id_,
        distance=distance_m,
        average_speed=speed,
        moving_time=int(distance_m / speed),
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


def test_predicted_time_present_for_athlete_with_upcoming_race():

    runner = make_runner(
        weekly_training_days=3,
        target_race="10 km",
        race_date="2026-08-15",
        target_time="00:50:00",
    )

    # 10km em 3000s (5:00/km) -> prevê exatamente 10km -> 3000s = 50:00
    history = TrainingHistory(activities=[_run(2, 7, 10_000, 10_000 / 3000)])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["target_time"] == "00:50:00"
    assert recap["predicted_time"]["formatted"] == "50:00"


def test_predicted_time_absent_without_a_real_race_goal():

    runner = make_runner(weekly_training_days=3)  # sem target_race/race_date

    history = TrainingHistory(activities=[_run(2, 7, 10_000, 10_000 / 3000)])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["predicted_time"] is None


def test_predicted_time_does_not_need_a_race_date():
    """Correção importante: a maioria dos atletas reais tem target_race
    declarado mas SEM race_date marcado. A previsão não pode depender de
    race_date (só usado pra contagem regressiva) — só da distância REAL
    declarada. Também não importa se uma eventual data já passou."""

    runner = make_runner(
        weekly_training_days=3,
        target_race="10 km",
        race_date="2026-07-15",  # data no passado (ou nem precisaria existir)
        target_time="00:50:00",
    )

    history = TrainingHistory(activities=[_run(2, 7, 10_000, 10_000 / 3000)])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    assert recap["predicted_time"] is not None
    assert recap["predicted_time"]["formatted"] == "50:00"


def test_predicted_time_uses_full_history_not_just_month_activities():
    """A previsão usa o histórico COMPLETO recebido, não só os treinos do
    mês recapitulado — a forma atual não deve ficar presa à borda do mês."""

    runner = make_runner(
        weekly_training_days=3,
        target_race="10 km",
        race_date="2026-08-15",
        target_time="00:50:00",
    )

    history = TrainingHistory(activities=[
        _run(2, 7, 10_000, 10_000 / 3000, id_=1),  # treino do mês, 5:00/km
        _run(20, 6, 10_000, 10_000 / 2400, id_=2),  # mês anterior, mais rápido (4:00/km)
    ])

    recap = MonthlyRecapBuilder.build(runner, history, JULY)

    # usa o esforço mais rápido (4:00/km, de JUNHO) como âncora -> 40:00,
    # não os 50:00 que sairiam se só o treino de julho fosse considerado
    assert recap["predicted_time"]["formatted"] == "40:00"
