from datetime import datetime

import pytest

from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence import (
    personal_record_repository as repo_module,
)
from tests.coach.factories import (
    make_activity,
    make_enriched_activity,
    make_runner,
)


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):

    monkeypatch.setattr(repo_module, "_STORAGE", tmp_path / "records")


def _run(day, month, distance_m, speed, id_):

    return make_activity(
        id=id_,
        distance=distance_m,
        average_speed=speed,
        start_date=datetime(2026, month, day, 7, 0, 0),
    )


def _feed(runner, activities, current):

    history = TrainingHistory(activities=activities)

    enriched = make_enriched_activity(activity=current)

    return PersonalRecordDetector.after_feedback(runner, history, enriched)


def test_cold_start_seeds_and_stays_silent():

    runner = make_runner()

    current = _run(1, 7, 10_000, 3.33, 1)

    assert _feed(runner, [current], current) is None


def test_longest_run_triggers_after_seed():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first], first)  # semeia (10km)

    second = _run(2, 7, 15_000, 3.33, 2)

    message = _feed(runner, [first, second], second)

    assert message is not None
    assert "15.0 km" in message


def test_shorter_run_after_seed_does_not_trigger():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first], first)

    second = _run(2, 7, 8_000, 3.33, 2)

    assert _feed(runner, [first, second], second) is None


def test_pace_band_triggers_with_margin_and_ignores_micro_improvement():

    runner = make_runner()

    # 6km @ pace 5:00/km (speed = 1000/(5*60) = 3.333...)
    first = _run(1, 7, 6_000, 1000 / (5 * 60), 1)

    _feed(runner, [first], first)  # semeia banda 5-8 com pace 5:00

    # melhora de 10s/km (bem acima da margem de 3s) -> dispara
    faster = _run(2, 7, 6_000, 1000 / (4.83 * 60), 2)

    message = _feed(runner, [first, faster], faster)

    assert message is not None
    assert "mais rápido na faixa de 5-8" in message

    # segunda melhora, agora de ~1s/km (abaixo da margem) -> silêncio
    tiny_improvement = _run(3, 7, 6_000, 1000 / (4.81 * 60), 3)

    assert _feed(
        runner, [first, faster, tiny_improvement], tiny_improvement,
    ) is None


def test_km_milestone_crossed_triggers_once():

    runner = make_runner()

    # histórico com 90km acumulados antes do treino de hoje
    base = [
        _run(d, 6, 9_000, 3.0, d) for d in range(1, 11)
    ]

    _feed(runner, base, base[-1])  # semeia com 90km (nenhum marco cruzado)

    today = _run(1, 7, 15_000, 3.0, 100)  # empurra pra 105km -> cruza 100

    message = _feed(runner, base + [today], today)

    assert message is not None
    assert "100 km" in message

    # próximo treino comum não recruza o mesmo marco
    tomorrow = _run(2, 7, 5_000, 3.0, 101)

    again = _feed(runner, base + [today, tomorrow], tomorrow)

    assert again is None or "100 km" not in again


def test_weekly_record_fires_once_per_week():

    runner = make_runner()

    # semana anterior: 20km (semente)
    seed_week = [_run(1, 6, 10_000, 3.0, 1), _run(2, 6, 10_000, 3.0, 2)]

    _feed(runner, seed_week, seed_week[-1])

    # nova semana (ISO diferente), primeiro treino já supera os 20km da
    # semana semeada
    week2_run1 = _run(6, 7, 25_000, 3.0, 3)  # segunda-feira

    first_message = _feed(
        runner, seed_week + [week2_run1], week2_run1,
    )

    assert first_message is not None
    assert "maior volume" in first_message

    # segundo treino NA MESMA semana (mesmo que aumente ainda mais o volume)
    # não repete a comemoração
    week2_run2 = _run(8, 7, 10_000, 3.0, 4)  # quarta-feira

    second_message = _feed(
        runner,
        seed_week + [week2_run1, week2_run2],
        week2_run2,
    )

    assert second_message is None


def test_reprocessing_same_activity_does_not_repeat_celebration():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first], first)

    second = _run(2, 7, 15_000, 3.33, 2)

    activities = [first, second]

    first_result = _feed(runner, activities, second)

    assert first_result is not None

    # reprocessar exatamente o mesmo treino (ex.: webhook duplicado) não
    # dispara a mesma comemoração de novo
    second_result = _feed(runner, activities, second)

    assert second_result is None


def test_multiple_records_in_one_run_combine_into_one_message():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first], first)  # semeia longest=10km, semana ~10km

    # semana seguinte, mesmo pace (sem PR de faixa) mas mais longa e com
    # mais km na semana -> bate corrida mais longa E semana de maior volume
    big = _run(8, 7, 11_500, 3.33, 2)

    message = _feed(runner, [first, big], big)

    assert message is not None
    assert "recordes" in message
    assert "11.5 km" in message
    assert "maior volume" in message


def test_external_coach_athlete_still_gets_celebrated():

    runner = make_runner(external_coach=True)

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first], first)

    second = _run(2, 7, 15_000, 3.33, 2)

    message = _feed(runner, [first, second], second)

    assert message is not None
