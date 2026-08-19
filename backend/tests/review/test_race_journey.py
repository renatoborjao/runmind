"""Recap da jornada até a prova: o builder computa os números da jornada
inteira (semanas, km, treinos, maior treino) + projeção/evolução, e o formatador
monta a mensagem encaminhável e emocional."""

from datetime import date, datetime
from unittest.mock import patch

from app.application.review.race_journey_builder import RaceJourneyBuilder
from app.application.review.race_journey_message_formatter import (
    RaceJourneyMessageFormatter,
)
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner

BUILDER_MOD = "app.application.review.race_journey_builder"


def _goal():
    return TrainingGoal(
        name="10 km sub-50", distance_km=10.0,
        target_time="00:50:00", race_date=date(2026, 8, 23),
    )


def _history():
    return TrainingHistory(activities=[
        make_activity(start_date=datetime(2026, 6, 1, 7, 0), distance=6000),
        make_activity(start_date=datetime(2026, 7, 1, 7, 0), distance=10000),
        make_activity(start_date=datetime(2026, 8, 1, 7, 0), distance=8000),
    ])


def _build():
    with (
        patch(f"{BUILDER_MOD}.today_local", return_value=date(2026, 8, 20)),
        patch(
            f"{BUILDER_MOD}.RaceTimePredictor.predict_formatted",
            return_value={"formatted": "52:00"},
        ),
        patch(
            f"{BUILDER_MOD}.FitnessReadingService.read_evolution",
            return_value=None,
        ),
    ):
        return RaceJourneyBuilder.build(make_runner(name="Renato"), _history(), _goal())


def test_builder_sums_the_whole_journey():

    journey = _build()

    assert journey["total_runs"] == 3
    assert journey["total_km"] == 24.0        # 6 + 10 + 8
    assert journey["longest_km"] == 10.0
    # 1º treino 01/06 -> hoje 20/08 ≈ 11 semanas
    assert journey["weeks"] == 11
    assert journey["race_label"]


def test_builder_none_without_history_or_race():

    goal = _goal()

    assert RaceJourneyBuilder.build(
        make_runner(name="R"), TrainingHistory(activities=[]), goal,
    ) is None

    no_race = TrainingGoal(
        name="saúde", distance_km=10.0, target_time=None, race_date=None,
    )

    assert RaceJourneyBuilder.build(
        make_runner(name="R"), _history(), no_race,
    ) is None


def test_formatter_is_shareable_and_emotional():

    journey = _build()

    msg = RaceJourneyMessageFormatter.format("Renato", journey)

    assert "Renato" in msg
    assert "24.0 km" in msg
    assert "11 semanas" in msg
    assert "Ritmind" in msg          # assinatura encaminhável
    assert "colher" in msg.lower()   # empurrão emocional
