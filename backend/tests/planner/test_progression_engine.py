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
        recent_adherence=[1.0],
        has_race=True,
        is_deload=False,
    )

    defaults.update(kwargs)

    return ProgressionEngine.next_weekly_volume(**defaults)


def test_no_history_returns_zero():

    base = _baseline(weekly=0.0)

    assert ProgressionEngine.next_weekly_volume(
        base, consistency=0, recent_adherence=[], has_race=False,
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


def test_first_week_progresses_without_prior_adherence():

    # sem semana anterior (lista vazia): sobe pela consistência
    assert _vol(recent_adherence=[]) == 16.5


# ==========================================================
# Regressão só após 2+ semanas (uma atípica isolada segura)
# ==========================================================

def test_single_missed_week_holds_not_regress():

    # UMA semana atípica (fez pouco) NÃO derruba o plano
    assert _vol(recent_adherence=[0.3]) == 15.0


def test_two_missed_weeks_regress():

    # duas semanas seguidas não cumpridas: recua pra recuperar (×0.9)
    assert _vol(recent_adherence=[0.3, 0.4]) == 13.5


def test_recovers_after_a_good_week_between_misses():

    # miss, depois semana boa: a última manda -> volta a subir
    assert _vol(recent_adherence=[0.3, 1.0]) == 16.5


def test_partial_last_week_holds():

    # última semana parcial (não cumpriu tudo, mas não é "miss"): segura
    assert _vol(recent_adherence=[0.8]) == 15.0


def test_capacity_ceiling_caps_growth():

    base = _baseline(weekly=19.0, maxw=18.0)

    # 19 * 1.10 = 20.9, mas o teto 18*1.1 = 19.8 corta
    assert ProgressionEngine.next_weekly_volume(
        base, consistency=100.0, recent_adherence=[1.0], has_race=True,
    ) == 19.8


def test_falling_trend_does_not_force_up():

    base = _baseline(trend="caindo")

    assert ProgressionEngine.next_weekly_volume(
        base, consistency=100.0, recent_adherence=[1.0], has_race=True,
    ) == 15.0


def test_deload_reduces_target():

    # 15 * 1.10 = 16.5, deload ×0.8 = 13.2
    assert _vol(is_deload=True) == 13.2
