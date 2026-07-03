from datetime import UTC, date, datetime, timedelta

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner


def _date_in_week(
    reference: date,
    weeks_ago: int,
    weekday_offset: int = 0,
) -> date:

    approx = reference - timedelta(weeks=weeks_ago)

    iso_year, iso_week, _ = approx.isocalendar()

    monday = date.fromisocalendar(iso_year, iso_week, 1)

    return monday + timedelta(days=weekday_offset)


def test_consistency_reflects_real_adherence_not_hardcoded():

    reference = datetime.now(UTC).date()

    runner = make_runner(weekly_training_days=3)

    dates = [
        _date_in_week(reference, weeks_ago, weekday_offset)
        for weeks_ago in range(4)
        for weekday_offset in range(3)
    ]

    activities = [
        make_activity(
            id=i,
            start_date=datetime(d.year, d.month, d.day, 7, 0, 0),
        )
        for i, d in enumerate(dates)
    ]

    history = TrainingHistory(activities=activities)

    assessment = TrainingAssessmentBuilder.build(runner, history)

    assert assessment.consistency == 100.0


def test_consistency_is_zero_with_no_training_history():

    runner = make_runner(weekly_training_days=4)

    history = TrainingHistory(activities=[])

    assessment = TrainingAssessmentBuilder.build(runner, history)

    assert assessment.consistency == 0.0
