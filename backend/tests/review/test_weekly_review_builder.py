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


def test_build_goal_race_countdown():
    """Atleta com prova futura: contagem regressiva de semanas."""

    runner = make_runner(
        goal="10 km sub-50", target_race="10 km", race_date="2026-08-15",
        target_time="00:50:00",
    )

    history = TrainingHistory(activities=[_run(0, 10000.0, 3000)])

    review = WeeklyReviewBuilder.build(runner, history, reference_date=REFERENCE)

    assert review["goal"]["has_race"] is True
    assert review["goal"]["weeks_to_race"] == 5  # 05/07 -> 15/08
    assert review["goal"]["name"] == "10 km sub-50"

    # previsão de prova (Riegel): 10km em 3000s (5:00/km) -> meta é 10km, o
    # esforço-âncora já É a distância da meta -> previsão = 3000s = "50:00",
    # exatamente batendo a meta declarada (delta 0)
    predicted = review["goal"]["predicted_time"]
    assert predicted["formatted"] == "50:00"
    assert predicted["delta_seconds"] == 0


def test_build_goal_no_predicted_time_without_real_run():
    """Sem esforço-âncora real (só caminhada, por exemplo) -> sem previsão,
    silêncio em vez de número inventado."""

    runner = make_runner(
        goal="10 km sub-50", target_race="10 km", race_date="2026-08-15",
        target_time="00:50:00",
    )

    walk = make_activity(
        start_date=MONDAY, distance=2000.0, moving_time=1200, sport="Walk",
    )

    history = TrainingHistory(activities=[walk])

    review = WeeklyReviewBuilder.build(runner, history, reference_date=REFERENCE)

    assert review["goal"]["predicted_time"] is None


def test_build_goal_no_predicted_time_without_a_scheduled_race():
    """Decisão do Renato: a previsão só vale pra quem TEM prova de verdade
    (data marcada) — uma distância de treino sem competição no horizonte
    não é "prova", então não recebe "se a prova fosse hoje"."""

    runner = make_runner(
        goal="10 km sub-50", target_race="10 km",
        target_time="00:50:00",
    )  # sem race_date

    history = TrainingHistory(activities=[_run(0, 10000.0, 3000)])

    review = WeeklyReviewBuilder.build(runner, history, reference_date=REFERENCE)

    assert review["goal"]["has_race"] is False
    assert review["goal"]["predicted_time"] is None


def test_build_goal_health_when_no_race():

    runner = make_runner(goal="saúde e emagrecer")

    history = TrainingHistory(activities=[_run(0, 10000.0, 3000)])

    review = WeeklyReviewBuilder.build(runner, history, reference_date=REFERENCE)

    assert review["goal"]["has_race"] is False
    assert review["goal"]["weeks_to_race"] is None
    assert review["goal"]["predicted_time"] is None


def test_build_longest_km_of_the_closing_week():

    runner = make_runner(weekly_training_days=3)

    history = TrainingHistory(
        activities=[
            _run(0, 8000.0, 2400),
            _run(0, 14000.0, 4600),   # o maior da semana que fecha
            _run(1, 20000.0, 6600),   # semana anterior: não conta
        ],
    )

    review = WeeklyReviewBuilder.build(runner, history, reference_date=REFERENCE)

    assert review["longest_km"] == 14.0
