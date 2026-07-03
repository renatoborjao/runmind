from datetime import date, datetime, timedelta

from app.application.review.weekly_review_builder import WeeklyReviewBuilder
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner

# domingo da semana ISO 27 de 2026 (segunda = 29/06)
REFERENCE = date(2026, 7, 5)

MONDAY = datetime(2026, 6, 29, 7, 0, 0)


def _run(weeks_ago: int, distance: float, moving_time: int):

    return make_activity(
        start_date=MONDAY - timedelta(weeks=weeks_ago),
        distance=distance,
        moving_time=moving_time,
    )


def test_build_assembles_comparison_trends_and_consistency():

    runner = make_runner(weekly_training_days=1)

    history = TrainingHistory(
        activities=[
            _run(weeks_ago, 10000.0, 3000)
            for weeks_ago in range(8)
        ],
    )

    review = WeeklyReviewBuilder.build(
        runner,
        history,
        reference_date=REFERENCE,
    )

    assert review["week_start"] == "2026-06-29"

    assert review["comparison"]["current_week"]["distance_km"] == 10.0
    assert review["comparison"]["previous_week"]["distance_km"] == 10.0

    assert review["trends"]["volume"]["direction"] == "stable"

    # 1 dia treinado por semana com meta de 1 dia/semana -> 100%
    assert review["consistency"] == 100.0
