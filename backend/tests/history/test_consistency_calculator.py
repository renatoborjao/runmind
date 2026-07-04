from datetime import date, datetime, timedelta

from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity

REFERENCE_DATE = date(2026, 7, 16)


def _date_in_week(weeks_ago: int, weekday_offset: int = 0) -> date:
    """Data dentro da semana ISO que fica `weeks_ago` semanas antes de
    REFERENCE_DATE — usa a segunda-feira daquela semana ISO como âncora
    para não cair acidentalmente numa semana vizinha."""

    approx = REFERENCE_DATE - timedelta(weeks=weeks_ago)

    iso_year, iso_week, _ = approx.isocalendar()

    monday = date.fromisocalendar(iso_year, iso_week, 1)

    return monday + timedelta(days=weekday_offset)


def _history_from_dates(*dates: date) -> TrainingHistory:

    activities = [
        make_activity(
            id=i,
            start_date=datetime(d.year, d.month, d.day, 7, 0, 0),
        )
        for i, d in enumerate(dates)
    ]

    return TrainingHistory(activities=activities)


def test_returns_zero_when_no_activities():

    history = TrainingHistory(activities=[])

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=4,
        reference_date=REFERENCE_DATE,
    )

    assert result == 0.0


def test_returns_zero_when_weekly_training_days_is_zero():

    history = _history_from_dates(_date_in_week(0))

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=0,
        reference_date=REFERENCE_DATE,
    )

    assert result == 0.0


def test_full_adherence_across_four_weeks():

    dates = [
        _date_in_week(weeks_ago, weekday_offset)
        for weeks_ago in range(4)
        for weekday_offset in range(3)
    ]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=3,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    assert result == 100.0


def test_partial_adherence_averages_across_weeks():

    # 1 dia treinado por semana, meta de 4 dias/semana -> 25% de média
    dates = [_date_in_week(weeks_ago) for weeks_ago in range(4)]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=4,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    assert result == 25.0


def test_multiple_activities_same_day_count_once():

    same_day = _date_in_week(0)

    activities = [
        make_activity(
            id=1,
            start_date=datetime.combine(same_day, datetime.min.time()),
        ),
        make_activity(
            id=2,
            start_date=datetime.combine(same_day, datetime.min.time())
            + timedelta(hours=12),
        ),
    ]

    history = TrainingHistory(activities=activities)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=4,
        weeks=1,
        reference_date=same_day,
    )

    assert result == 25.0


def test_empty_week_between_trained_weeks_pulls_average_down():

    # Treinou nas semanas 1 e 3 (completas), falhou a semana 2
    dates = [
        _date_in_week(weeks_ago, weekday_offset)
        for weeks_ago in (1, 3)
        for weekday_offset in range(3)
    ]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=3,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    # janela recortada ao início do histórico: semanas 1-3
    # (100% + 0% + 100%) / 3
    assert result == 66.7


def test_current_incomplete_week_does_not_drag_average_down():

    # 4 semanas completas perfeitas; semana em curso ainda sem treino
    dates = [
        _date_in_week(weeks_ago, weekday_offset)
        for weeks_ago in range(1, 5)
        for weekday_offset in range(3)
    ]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=3,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    assert result == 100.0


def test_rookie_with_history_only_in_current_week_scores_current_week():

    # Corredor estreante: todo o histórico está na semana em curso
    dates = [
        _date_in_week(0, weekday_offset)
        for weekday_offset in range(3)
    ]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=3,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    assert result == 100.0


def test_weeks_before_first_activity_are_not_counted():

    # Corredor na 2ª semana, treinando perfeitamente a semana completa
    dates = [
        _date_in_week(1, weekday_offset)
        for weekday_offset in range(3)
    ]

    history = _history_from_dates(*dates)

    result = ConsistencyCalculator.calculate(
        history,
        weekly_training_days=3,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    # sem o recorte, as 3 semanas vazias anteriores dariam 25%
    assert result == 100.0


def test_evaluated_weeks_counts_only_weeks_since_first_activity():

    # Histórico começa 2 semanas atrás: só as semanas 1 e 2 são avaliadas
    dates = [_date_in_week(weeks_ago) for weeks_ago in (1, 2)]

    history = _history_from_dates(*dates)

    weeks = ConsistencyCalculator.evaluated_weeks(
        history,
        weeks=4,
        reference_date=REFERENCE_DATE,
    )

    assert weeks == 2


def test_evaluated_weeks_zero_without_activities():

    history = TrainingHistory(activities=[])

    assert (
        ConsistencyCalculator.evaluated_weeks(
            history,
            reference_date=REFERENCE_DATE,
        )
        == 0
    )


def test_evaluated_weeks_rookie_current_week_counts_as_one():

    # Todo o histórico na semana em curso: avalia a própria semana
    dates = [_date_in_week(0, offset) for offset in range(3)]

    history = _history_from_dates(*dates)

    weeks = ConsistencyCalculator.evaluated_weeks(
        history,
        reference_date=REFERENCE_DATE,
    )

    assert weeks == 1
