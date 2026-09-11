from app.application.history.stimulus_result import (
    STIMULUS_HIT,
    STIMULUS_MISS,
    STIMULUS_PARTIAL,
    stimulus_result_from_comparison,
)
from app.domain.entities.block_comparison import BlockComparison, ExecutedBlock
from app.domain.entities.workout_step import INTERVAL, RUN, WARMUP


def _interval(within, n=1):

    return ExecutedBlock(
        kind=INTERVAL, label=f"Tiro {n}",
        planned_distance_m=1000.0, planned_duration_sec=None,
        pace_min="4:30", pace_max="4:40",
        executed_distance_m=1000.0, executed_duration_sec=270.0,
        executed_pace=4.5, executed_hr=175, within_target=within,
    )


def _warmup():

    return ExecutedBlock(
        kind=WARMUP, label="Aquecimento",
        planned_distance_m=1000.0, planned_duration_sec=None,
        pace_min=None, pace_max=None,
        executed_distance_m=1000.0, executed_duration_sec=360.0,
        executed_pace=6.0, executed_hr=140, within_target=None,
    )


def test_hit_when_most_intervals_on_target():
    # 4 de 5 tiros no alvo → HIT
    blocks = [_warmup()] + [_interval(i < 4, i) for i in range(5)]

    result = stimulus_result_from_comparison(BlockComparison(blocks=blocks))

    assert result["verdict"] == STIMULUS_HIT
    assert result["on_target"] == 4
    assert result["total"] == 5


def test_miss_when_few_on_target():
    # 1 de 5 no alvo → MISS (correu os tiros fora do ritmo)
    blocks = [_interval(i < 1, i) for i in range(5)]

    result = stimulus_result_from_comparison(BlockComparison(blocks=blocks))

    assert result["verdict"] == STIMULUS_MISS


def test_partial_middle_ground():
    # 2 de 5 (0.4) → PARTIAL
    blocks = [_interval(i < 2, i) for i in range(5)]

    result = stimulus_result_from_comparison(BlockComparison(blocks=blocks))

    assert result["verdict"] == STIMULUS_PARTIAL


def test_missing_intervals_count_against():
    # fez 3 tiros no alvo, mas 2 "Tiro" faltaram (parou a série) → 3/5 = PARTIAL
    blocks = [_interval(True, i) for i in range(3)]

    comparison = BlockComparison(blocks=blocks, missing=["Tiro 4", "Tiro 5"])

    result = stimulus_result_from_comparison(comparison)

    assert result["total"] == 5
    assert result["on_target"] == 3
    assert result["verdict"] == STIMULUS_PARTIAL


def test_none_when_no_intervals():
    # treino contínuo (só corrida) → não é tiro, sem veredito
    blocks = [
        ExecutedBlock(
            kind=RUN, label="Corrida contínua",
            planned_distance_m=8000.0, planned_duration_sec=None,
            pace_min="6:00", pace_max="6:20",
            executed_distance_m=8000.0, executed_duration_sec=2900.0,
            executed_pace=6.04, executed_hr=150, within_target=True,
        )
    ]

    assert stimulus_result_from_comparison(BlockComparison(blocks=blocks)) is None


def test_none_when_comparison_missing():
    assert stimulus_result_from_comparison(None) is None
