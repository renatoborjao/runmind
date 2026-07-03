from app.application.history.metrics_resolver import MetricsResolver
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner


def test_with_history_uses_real_metrics():

    # 10 km em 3000 s (5:00 min/km)
    history = TrainingHistory(
        activities=[make_activity(average_speed=3.33)],
    )

    metrics = MetricsResolver.resolve(make_runner(), history)

    # derivado do pace real (~5.0), não dos defaults de estreante
    assert 4.5 < metrics.easy_pace_min < 5.0


def test_without_history_uses_declared_pace_and_volume():

    runner = make_runner(
        initial_pace_min_km=6.4,
        initial_weekly_km=15.0,
    )

    metrics = MetricsResolver.resolve(
        runner,
        TrainingHistory(activities=[]),
    )

    assert metrics.easy_pace_min == 6.15  # 6.4 - 0.25
    assert metrics.easy_pace_max == 6.75  # 6.4 + 0.35
    assert metrics.vo2_pace == 5.3  # 6.4 - 1.10
    assert metrics.weekly_volume == 15.0
    assert metrics.max_long_run == 5.2  # round(15 * 0.35, 1)


def test_rookie_defaults_when_nothing_declared():

    metrics = MetricsResolver.resolve(
        make_runner(),
        TrainingHistory(activities=[]),
    )

    assert metrics.easy_pace_min == 7.75  # 8.0 - 0.25
    assert metrics.weekly_volume == 6.0
    assert metrics.max_long_run == 3.0
