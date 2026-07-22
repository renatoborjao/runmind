from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history.training_load_analyzer import (
    TrainingLoadAnalyzer,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_load import (
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
)

REF = date(2026, 7, 22)


def _act(days_ago: int, minutes: int):
    """Atividade mínima: só o que o analisador usa (start_date + moving_time)."""

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 10, 0),
        moving_time=minutes * 60,
    )


def _analyze(activities):

    return TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=activities),
        reference_date=REF,
    )


def test_optimal_when_load_is_steady():

    # 60 min/dia por 28 dias -> aguda = crônica -> ACWR ~1.0
    load = _analyze([_act(d, 60) for d in range(28)])

    assert load.acute_load == 420.0
    assert load.chronic_load == 420.0
    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_high_when_ramping_fast():

    # base fraca + pico nos últimos 7 dias -> ACWR bem acima de 1.5
    acts = [_act(27, 30)] + [_act(d, 60) for d in range(7)]

    load = _analyze(acts)

    assert load.acwr > 1.5
    assert load.status == LOAD_HIGH


def test_detraining_when_acute_drops():

    # carregou 21 dias e parou na última semana -> aguda 0 -> ACWR 0
    load = _analyze([_act(d, 60) for d in range(7, 28)])

    assert load.acute_load == 0.0
    assert load.acwr == 0.0
    assert load.status == LOAD_DETRAINING


def test_insufficient_history_overrides_ratio():

    # só 5 dias de histórico: mesmo com ACWR alto, não arrisca veredito
    load = _analyze([_act(d, 60) for d in range(5)])

    assert load.days_of_history == 5
    assert load.status == LOAD_INSUFFICIENT


def test_weekly_loads_ordered_old_to_new():

    acts = [_act(0, 10), _act(7, 20), _act(14, 30), _act(21, 40)]

    load = _analyze(acts)

    assert load.weekly_loads == [40.0, 30.0, 20.0, 10.0]


def test_empty_history_is_insufficient():

    load = _analyze([])

    assert load.acute_load == 0.0
    assert load.chronic_load == 0.0
    assert load.acwr is None
    assert load.status == LOAD_INSUFFICIENT
    assert load.days_of_history == 0
    assert load.weekly_loads == [0.0, 0.0, 0.0, 0.0]
