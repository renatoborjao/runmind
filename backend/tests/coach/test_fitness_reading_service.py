from datetime import datetime
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from tests.coach.factories import make_activity

MODULE = "app.application.coach.intelligence.fitness_reading_service"


def test_without_races_excludes_race_day_from_ef_base():
    """A PROVA sai da base de eficiência aeróbica (esforço máx com taper/
    adrenalina distorce a curva de economia). Segue contando pra forma noutros
    eixos (VDOT/previsão), só não no EF. Decisão do Renato."""

    race_day = make_activity(id=1, start_date=datetime(2026, 8, 23, 8, 0))
    easy = make_activity(id=2, start_date=datetime(2026, 8, 20, 7, 0))

    repo = MagicMock()
    repo.load.return_value = [{"date": "2026-08-23"}]

    with patch(f"{MODULE}.RaceResultRepository", return_value=repo):

        result = FitnessReadingService._without_races(
            "renato2", [race_day, easy],
        )

    assert [a.id for a in result] == [2]


def test_without_races_noop_when_no_race_recorded():

    easy = make_activity(id=2, start_date=datetime(2026, 8, 20, 7, 0))

    repo = MagicMock()
    repo.load.return_value = []

    with patch(f"{MODULE}.RaceResultRepository", return_value=repo):

        result = FitnessReadingService._without_races("renato2", [easy])

    assert result == [easy]


def test_max_hr_prefers_higher_of_observed_and_tanaka():
    """FC máx = maior entre a MEDIDA (pico real em corrida) e Tanaka. Se o
    atleta bateu 190 e Tanaka estima 185, vale o real (190)."""

    acts = [make_activity(id=1, max_heartrate=190.0)]

    # idade 33 -> Tanaka ~185
    assert FitnessReadingService._max_hr(33, acts) == 190


def test_max_hr_falls_back_to_tanaka_when_observed_is_lower():
    """Nunca foi ao máximo (pico 170) -> usa Tanaka (185), melhor estimativa
    do teto verdadeiro."""

    acts = [make_activity(id=1, max_heartrate=170.0)]

    assert FitnessReadingService._max_hr(33, acts) == round(208 - 0.7 * 33)


def test_observed_ignores_sensor_spikes():
    """Leitura absurda (240 = sensor travado) é descartada da FC máx medida."""

    acts = [
        make_activity(id=1, max_heartrate=240.0),   # spike, fora da faixa
        make_activity(id=2, max_heartrate=188.0),
    ]

    assert FitnessReadingService._observed_max_hr(acts) == 188


def test_max_hr_none_without_age_or_data():

    assert FitnessReadingService._max_hr(None, []) is None


def test_observed_only_counts_runs():
    """Pico de FC de musculação/pedal não define a FC máx de corrida."""

    acts = [make_activity(id=1, sport="WeightTraining", max_heartrate=200.0)]

    assert FitnessReadingService._observed_max_hr(acts) is None
