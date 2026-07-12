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


def test_walks_and_fragments_dont_slow_the_pace():
    """Bug da Fernanda: ela corre ~5:00-6:00, mas caminhadas (11-12 min/km) e
    fragmentos curtos no histórico puxavam a média e o plano prescrevia paces
    lentos demais. Só corridas de verdade (>=1.5km, <9min/km) contam."""

    def _run(id_, km, pace):
        return make_activity(
            id=id_, distance=km * 1000, average_speed=1000 / (pace * 60),
        )

    history = TrainingHistory(activities=[
        _run(1, 8.0, 5.0),
        _run(2, 6.0, 5.2),
        _run(3, 10.0, 5.1),
        _run(4, 4.0, 11.0),    # caminhada — fora
        _run(5, 0.5, 6.0),     # fragmento curto — fora
    ])

    metrics = MetricsResolver.resolve(make_runner(), history)

    # pace de referência ~5:1 (mediana das corridas), não ~6:5 (com a caminhada)
    assert 4.6 < metrics.easy_pace_min < 5.3


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
