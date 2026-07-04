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


def test_empty_history_uses_declared_volume_without_progression():

    runner = make_runner(initial_weekly_km=10.0, weekly_training_days=2)

    assessment = TrainingAssessmentBuilder.build(
        runner,
        TrainingHistory(activities=[]),
    )

    assert assessment.current_weekly_volume == 10.0
    # sem +8% na primeira semana (conservador)
    assert assessment.recommended_weekly_volume == 10.0
    assert assessment.longest_run == 5.0  # 10 km / 2 dias


def test_empty_history_without_declared_volume_uses_rookie_floor():

    assessment = TrainingAssessmentBuilder.build(
        make_runner(),
        TrainingHistory(activities=[]),
    )

    assert assessment.current_weekly_volume == 6.0
    assert assessment.recommended_weekly_volume == 6.0


def test_level_is_intermediate_when_longest_run_high_despite_low_volume():

    # volume semanal moderado mas maior treino de 12 km: não é iniciante
    runner = make_runner(weekly_training_days=3)

    history = TrainingHistory(
        activities=[
            make_activity(
                id=1,
                distance=12000.0,
                start_date=datetime(2026, 7, 10, 7, 0, 0),
            ),
        ],
    )

    assessment = TrainingAssessmentBuilder.build(runner, history)

    assert assessment.longest_run == 12.0
    assert assessment.level == "Intermediate"


def test_level_is_beginner_when_low_volume_and_short_runs():

    runner = make_runner(weekly_training_days=3, initial_weekly_km=8.0)

    assessment = TrainingAssessmentBuilder.build(
        runner,
        TrainingHistory(activities=[]),
    )

    assert assessment.level == "Beginner"
