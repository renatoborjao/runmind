from app.application.history.metrics_resolver import MetricsResolver
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner


def test_with_history_uses_real_metrics():

    # 10 km em 3000 s (5:00 min/km) -> VDOT ~40; fácil ancorado no Daniels
    history = TrainingHistory(
        activities=[make_activity(average_speed=3.33)],
    )

    metrics = MetricsResolver.resolve(make_runner(), history)

    # fácil grounded (~5:59 pro VDOT 40), não os defaults de estreante
    assert 5.8 < metrics.easy_pace_min < 6.15


def test_walks_and_fragments_dont_anchor_the_pace():
    """Bug da Fernanda: caminhadas (11-12 min/km) e fragmentos curtos no
    histórico não podem ancorar o modelo. Só corridas de verdade (>=2km,
    <9min/km) contam pro VDOT e pro ritmo leve real."""

    def _run(id_, km, pace):
        return make_activity(
            id=id_, distance=km * 1000, average_speed=1000 / (pace * 60),
        )

    history = TrainingHistory(activities=[
        _run(1, 8.0, 5.0),
        _run(2, 6.0, 5.2),
        _run(3, 10.0, 5.1),
        _run(4, 4.0, 11.0),    # caminhada — fora (pace > 9)
        _run(5, 0.5, 6.0),     # fragmento curto — fora (< 2 km)
    ])

    metrics = MetricsResolver.resolve(make_runner(), history)

    # fácil ancorado nas corridas de verdade (~5:55), não puxado pela caminhada
    assert 5.5 < metrics.easy_pace_min < 6.2


def test_without_history_uses_declared_pace_and_volume():

    runner = make_runner(
        initial_pace_min_km=6.4,
        initial_weekly_km=15.0,
    )

    metrics = MetricsResolver.resolve(
        runner,
        TrainingHistory(activities=[]),
    )

    # fallback conservador do pace declarado (fonte única)
    assert metrics.easy_pace_min == 6.4
    assert metrics.easy_pace_max == 6.95   # 6.4 + 0.55
    assert metrics.vo2_pace == 5.5         # 6.4 - 0.90
    assert metrics.weekly_volume == 15.0
    assert metrics.max_long_run == 5.2     # round(15 * 0.35, 1)


def test_rookie_defaults_when_nothing_declared():

    metrics = MetricsResolver.resolve(
        make_runner(),
        TrainingHistory(activities=[]),
    )

    assert metrics.easy_pace_min == 8.0
    assert metrics.weekly_volume == 6.0
    assert metrics.max_long_run == 3.0
