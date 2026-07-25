from datetime import date, timedelta

from app.application.history.trend_estimator import TrendEstimator
from app.domain.entities.signal_trend import (
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_STABLE,
)

D0 = date(2026, 5, 1)


def _series(values, step_days=7):
    """Uma amostra por semana, valores na ordem dada."""

    return [(D0 + timedelta(days=i * step_days), v) for i, v in enumerate(values)]


def test_rising_series_is_improving():

    trend = TrendEstimator.estimate(
        _series([1.00, 1.02, 1.04, 1.06, 1.08, 1.10, 1.12, 1.14]),
        noise_pct=0.02, min_points=6, min_span_days=14,
    )

    assert trend is not None
    assert trend.direction == TREND_IMPROVING
    assert trend.relative_change > 0
    assert trend.recent_value > trend.earlier_value
    assert trend.r_squared > 0.9        # reta quase perfeita


def test_falling_series_is_declining():

    trend = TrendEstimator.estimate(
        _series([1.14, 1.12, 1.10, 1.08, 1.06, 1.04, 1.02, 1.00]),
        noise_pct=0.02, min_points=6, min_span_days=14,
    )

    assert trend.direction == TREND_DECLINING
    assert trend.relative_change < 0


def test_flat_series_is_stable():

    trend = TrendEstimator.estimate(
        _series([1.00, 1.005, 0.998, 1.002, 1.001, 0.999, 1.003, 1.0]),
        noise_pct=0.02, min_points=6, min_span_days=14,
    )

    assert trend.direction == TREND_STABLE


def test_invert_treats_falling_as_improving():
    """FC de repouso caindo = melhora (invert=True)."""

    trend = TrendEstimator.estimate(
        _series([62, 61, 60, 59, 58, 57]),
        noise_pct=0.02, min_points=6, min_span_days=14, invert=True,
    )

    assert trend.direction == TREND_IMPROVING
    assert trend.relative_change > 0        # orientado: melhora positiva
    assert trend.recent_value < trend.earlier_value   # o valor cru caiu


def test_too_few_points_returns_none():

    assert TrendEstimator.estimate(
        _series([1.0, 1.1, 1.2]),
        noise_pct=0.02, min_points=6, min_span_days=14,
    ) is None


def test_short_span_returns_none():
    """6 pontos amontoados em poucos dias não é tendência."""

    dense = [(D0 + timedelta(days=i), 1.0 + i * 0.01) for i in range(6)]

    assert TrendEstimator.estimate(
        dense, noise_pct=0.02, min_points=6, min_span_days=14,
    ) is None


def test_outlier_does_not_flip_direction():
    """Um treino atípico não vira a tendência (vantagem da regressão sobre
    metade-vs-metade)."""

    values = [1.00, 1.02, 1.04, 0.80, 1.08, 1.10, 1.12, 1.14]  # 0.80 = outlier

    trend = TrendEstimator.estimate(
        _series(values), noise_pct=0.02, min_points=6, min_span_days=14,
    )

    assert trend.direction == TREND_IMPROVING
