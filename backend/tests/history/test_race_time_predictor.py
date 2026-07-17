from datetime import datetime

from app.application.history.race_time_predictor import RaceTimePredictor
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity


def _run(distance_m, speed, sport="Run", id_=1, day=1, month=7):

    return make_activity(
        id=id_,
        sport=sport,
        distance=distance_m,
        average_speed=speed,
        moving_time=int(distance_m / speed),
        start_date=datetime(2026, month, day, 7, 0, 0),
    )


def test_no_real_run_returns_none():

    history = TrainingHistory(activities=[
        _run(2_000, 3.0, id_=1),  # abaixo do mínimo de âncora (3km)
    ])

    assert RaceTimePredictor.predict(history, goal_distance_km=10.0) is None


def test_walk_is_not_used_as_anchor():

    history = TrainingHistory(activities=[
        _run(5_000, 3.0, sport="Walk", id_=1),  # sport não é corrida real
    ])

    assert RaceTimePredictor.predict(history, goal_distance_km=10.0) is None


def test_picks_the_fastest_pace_as_anchor_not_the_longest():

    history = TrainingHistory(activities=[
        _run(10_000, 3.0, id_=1),   # pace ~5:33/km
        _run(5_000, 3.5, id_=2),    # pace ~4:45/km — mais rápido
    ])

    result = RaceTimePredictor.predict(history, goal_distance_km=10.0)

    assert result is not None
    assert result["anchor_distance_km"] == 5.0


def test_riegel_math_matches_hand_calculation():

    # 5km em 1200s (4:00/km) -> prever 10km
    history = TrainingHistory(activities=[_run(5_000, 5_000 / 1200, id_=1)])

    result = RaceTimePredictor.predict(history, goal_distance_km=10.0)

    expected = 1200 * (10.0 / 5.0) ** 1.06

    assert result["predicted_seconds"] == expected


def test_extrapolation_ratio_too_large_returns_none():

    # âncora de 3km pra prever uma maratona (42km) -> razão ~14x, corta
    history = TrainingHistory(activities=[_run(3_000, 3.5, id_=1)])

    assert RaceTimePredictor.predict(history, goal_distance_km=42.2) is None


def test_ratio_within_bound_still_predicts():

    # âncora de 10km pra prever 21km -> razão 2.1x, dentro do limite de 4x
    history = TrainingHistory(activities=[_run(10_000, 3.0, id_=1)])

    result = RaceTimePredictor.predict(history, goal_distance_km=21.1)

    assert result is not None


def test_anchor_date_is_carried():

    history = TrainingHistory(activities=[_run(5_000, 3.0, id_=1, day=15)])

    result = RaceTimePredictor.predict(history, goal_distance_km=10.0)

    assert result["anchor_date"] == "2026-07-15"
