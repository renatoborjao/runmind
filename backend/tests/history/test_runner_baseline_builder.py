from datetime import datetime, timedelta

from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity

# âncora numa segunda-feira ISO pra os buckets semanais ficarem limpos
MONDAY = datetime(2026, 6, 1, 7, 0, 0)  # 2026-06-01 é segunda


def _act(week: int, day: int, km: float, aid: int):
    """Corrida na semana `week` (0 = mais antiga), dia `day` da semana."""

    when = MONDAY + timedelta(weeks=week, days=day)

    return make_activity(
        id=aid,
        start_date=when,
        distance=km * 1000,
        average_speed=3.0,
    )


def test_empty_history_has_no_baseline():

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=[]))

    assert base.has_history is False
    assert base.weekly_km == 0.0
    assert base.runs_per_week == 0.0


def test_imported_plan_floors_a_thin_strava_baseline():

    # Strava fino (~5 km/sem) + plano importado de 40 km/5 dias:
    # o baseline não fica abaixo do plano — o motor planeja nesse nível.
    from tests.coach.factories import make_runner

    runner = make_runner(plan_baseline={
        "weekly_km": 40.0, "runs_per_week": 5,
        "typical_km": 7.0, "longest_km": 12.0,
    })

    acts = [_act(0, 0, 5.0, 1), _act(1, 0, 5.0, 2)]

    base = RunnerBaselineBuilder.build(TrainingHistory(acts), runner)

    assert base.weekly_km == 40.0
    assert base.longest_km == 12.0
    assert base.typical_run_km == 7.0
    assert base.max_week_km >= 40.0   # eleva o teto de capacidade também


def test_real_strava_above_the_import_wins():

    # quando o Strava real supera o plano importado, o real assume
    from tests.coach.factories import make_runner

    runner = make_runner(plan_baseline={
        "weekly_km": 10.0, "runs_per_week": 2,
        "typical_km": 4.0, "longest_km": 6.0,
    })

    acts = [
        _act(0, 0, 10.0, 1), _act(0, 2, 10.0, 2),
        _act(1, 0, 10.0, 3), _act(1, 2, 10.0, 4),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(acts), runner)

    # semana real de 20 km > piso de 10 -> real assume
    assert base.weekly_km == 20.0


def test_typical_run_is_median_not_the_longest():

    # 4 rodagens de 5 km e um longão de 15 km: típico = 5, não a média
    acts = [
        _act(0, 0, 5.0, 1),
        _act(0, 2, 5.0, 2),
        _act(1, 0, 5.0, 3),
        _act(1, 2, 5.0, 4),
        _act(1, 5, 15.0, 5),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=acts))

    assert base.typical_run_km == 5.0
    assert base.longest_km == 15.0


def test_runs_per_week_counts_only_active_weeks():

    # semana 0: 3 corridas; semana 1: 3 corridas -> 3.0/semana
    acts = [
        _act(0, 0, 5.0, 1), _act(0, 2, 5.0, 2), _act(0, 4, 5.0, 3),
        _act(1, 0, 5.0, 4), _act(1, 2, 5.0, 5), _act(1, 4, 5.0, 6),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=acts))

    assert base.runs_per_week == 3.0


def test_trend_rising_when_recent_weeks_bigger():

    # 4 semanas: 10, 10, 20, 20 km -> subindo
    acts = [
        _act(0, 0, 10.0, 1),
        _act(1, 0, 10.0, 2),
        _act(2, 0, 20.0, 3),
        _act(3, 0, 20.0, 4),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=acts))

    assert base.trend == "subindo"


def test_trend_stable_within_band():

    acts = [
        _act(0, 0, 10.0, 1),
        _act(1, 0, 10.0, 2),
        _act(2, 0, 10.0, 3),
        _act(3, 0, 10.0, 4),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=acts))

    assert base.trend == "estável"


def test_falling_trend_when_recent_weeks_smaller():

    acts = [
        _act(0, 0, 20.0, 1),
        _act(1, 0, 20.0, 2),
        _act(2, 0, 10.0, 3),
        _act(3, 0, 10.0, 4),
    ]

    base = RunnerBaselineBuilder.build(TrainingHistory(activities=acts))

    assert base.trend == "caindo"
