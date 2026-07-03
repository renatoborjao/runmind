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


def test_empty_week_scores_zero_and_pulls_average_down():

    # Semana atual cheia, semanas anteriores vazias
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

    assert result == 25.0
