from app.application.history.training_reality_analyzer import (
    ALIGNED,
    OVER,
    UNDER,
    TrainingRealityAnalyzer,
    training_reality_directive,
)
from app.domain.entities.runner_baseline import RunnerBaseline


def _baseline(runs_per_week, weekly_km=25.0, has_history=True) -> RunnerBaseline:

    return RunnerBaseline(
        has_history=has_history,
        weekly_km=weekly_km,
        last_week_km=weekly_km,
        max_week_km=weekly_km,
        runs_per_week=runs_per_week,
        typical_run_km=6.0,
        longest_km=12.0,
        trend="estável",
    )


def test_over_delivery_when_runs_more_than_registered():
    """Hélio: registrou 3, corre ~5x -> descolamento 'over'."""

    v = TrainingRealityAnalyzer.assess(3, _baseline(5.0, weekly_km=28.0))

    assert v.verdict == OVER
    d = training_reality_directive(v)
    assert "5x" in d and "28 km" in d and "dimensione" in d.lower()


def test_under_delivery_when_runs_less_than_registered():

    v = TrainingRealityAnalyzer.assess(4, _baseline(2.0, weekly_km=12.0))

    assert v.verdict == UNDER
    assert "cumpre" in training_reality_directive(v)


def test_aligned_when_reality_matches_registration():

    v = TrainingRealityAnalyzer.assess(3, _baseline(3.0))

    assert v.verdict == ALIGNED
    assert training_reality_directive(v) == ""


def test_small_gap_is_aligned_not_flagged():
    """3 registrados x 3.5 reais é ruído de rotina, não descolamento."""

    v = TrainingRealityAnalyzer.assess(3, _baseline(3.5))

    assert v.verdict == ALIGNED


def test_no_real_history_never_asserts():
    """Só declarado (sem Strava): não afirma nada — evita chutar no vácuo."""

    v = TrainingRealityAnalyzer.assess(3, _baseline(6.0, has_history=False))

    assert v.verdict == ALIGNED
    assert training_reality_directive(v) == ""


def test_zero_registered_or_zero_real_is_aligned():

    assert TrainingRealityAnalyzer.assess(0, _baseline(5.0)).verdict == ALIGNED
    assert TrainingRealityAnalyzer.assess(3, _baseline(0.0)).verdict == ALIGNED
