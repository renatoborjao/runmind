from app.application.planner.engines.progression_engine import (
    ProgressionEngine,
)
from app.domain.entities.runner_baseline import RunnerBaseline


def _baseline(weekly=15.0, maxw=18.0, trend="estável") -> RunnerBaseline:

    return RunnerBaseline(
        has_history=True,
        weekly_km=weekly,
        last_week_km=weekly,
        max_week_km=maxw,
        runs_per_week=3.0,
        typical_run_km=6.0,
        longest_km=12.0,
        trend=trend,
    )


def _vol(**kwargs):

    defaults = dict(
        baseline=_baseline(),
        consistency=100.0,
        adherence=1.0,
        has_race=True,
        is_deload=False,
    )

    defaults.update(kwargs)

    return ProgressionEngine.next_weekly_volume(**defaults)


def test_no_history_returns_zero():

    base = _baseline(weekly=0.0)

    assert ProgressionEngine.next_weekly_volume(
        base, consistency=0, adherence=None, has_race=False,
    ) == 0.0


def test_consistent_athlete_steps_up_more():

    high = _vol(consistency=100.0)   # 15 * 1.10 = 16.5
    low = _vol(consistency=40.0)     # 15 * 1.02 = 15.3

    assert high == 16.5
    assert low == 15.3
    assert high > low


def test_health_goal_progresses_gentler_than_race():

    race = _vol(has_race=True, consistency=100.0)     # 1.10
    health = _vol(has_race=False, consistency=100.0)  # 1.05

    assert race == 16.5
    assert health == 15.8
    assert health < race


def test_poor_adherence_recovers():

    # cumpriu menos da metade da semana passada: recua (×0.9)
    assert _vol(adherence=0.3) == 13.5


def test_partial_adherence_holds():

    # cumpriu em parte: segura a carga (×1.0)
    assert _vol(adherence=0.7) == 15.0


def test_capacity_ceiling_caps_growth():

    # volume já perto da melhor semana: teto = 18 * 1.1 = 19.8
    base = _baseline(weekly=19.0, maxw=18.0)

    # 19 * 1.10 = 20.9, mas o teto 19.8 corta
    assert ProgressionEngine.next_weekly_volume(
        base, consistency=100.0, adherence=1.0, has_race=True,
    ) == 19.8


def test_falling_trend_does_not_force_up():

    base = _baseline(trend="caindo")

    # mesmo consistente, tendência caindo segura em ×1.0
    assert ProgressionEngine.next_weekly_volume(
        base, consistency=100.0, adherence=1.0, has_race=True,
    ) == 15.0


def test_deload_reduces_target():

    # 15 * 1.10 = 16.5, deload ×0.8 = 13.2
    assert _vol(is_deload=True) == 13.2
