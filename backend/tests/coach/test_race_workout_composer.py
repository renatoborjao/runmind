from app.application.coach.planning.race_strategy_engine import RacePacePlan
from app.application.coach.planning.race_workout_composer import (
    RaceWorkoutComposer,
)
from app.application.planner.pace_formatter import PaceFormatter


def _plan(distance_km=10.0, avg_pace_min=5.5):

    return RacePacePlan(
        distance_km=distance_km,
        estimated=False,
        total_minutes=avg_pace_min * distance_km,
        avg_pace_min=avg_pace_min,
        open_pace_min=avg_pace_min + 5 / 60,
        close_pace_min=avg_pace_min - 5 / 60,
        halfway_minutes=(avg_pace_min + 5 / 60) * distance_km / 2,
    )


def _sec(pace_str):

    m, s = pace_str.split(":")
    return int(m) * 60 + int(s)


def test_four_blocks_covering_full_distance():

    steps = RaceWorkoutComposer.compose(_plan(distance_km=10.0))

    assert len(steps) == 4
    assert sum(s.distance_m for s in steps) == 10000


def test_negative_split_controlled_start_strong_finish():
    """Primeiro bloco mais LENTO que o último (a defesa contra quebrar)."""

    steps = RaceWorkoutComposer.compose(_plan(avg_pace_min=5.5))

    first_center = (_sec(steps[0].pace_min) + _sec(steps[0].pace_max)) / 2
    last_center = (_sec(steps[-1].pace_min) + _sec(steps[-1].pace_max)) / 2

    assert first_center > last_center  # começa devagar, fecha forte
    # cada bloco tem faixa de pace (zona que o relógio guia)
    assert all(s.pace_min and s.pace_max for s in steps)


def test_weighted_average_matches_target_pace():
    """A média ponderada pela distância bate o pace-alvo (5:30/km = 330s)."""

    steps = RaceWorkoutComposer.compose(_plan(avg_pace_min=5.5))

    total_m = sum(s.distance_m for s in steps)
    weighted = sum(
        ((_sec(s.pace_min) + _sec(s.pace_max)) / 2) * s.distance_m
        for s in steps
    ) / total_m

    assert abs(weighted - 330) < 1  # ~5:30/km


def test_pace_min_is_faster_end():
    """pace_min é a ponta RÁPIDA (segundos menores) — contrato do WorkoutStep."""

    steps = RaceWorkoutComposer.compose(_plan())

    for s in steps:

        assert _sec(s.pace_min) < _sec(s.pace_max)
        # sanidade: formatação válida
        assert PaceFormatter.format(_sec(s.pace_min) / 60)
