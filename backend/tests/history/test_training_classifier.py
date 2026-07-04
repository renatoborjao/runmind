from app.application.history.training_classifier import (
    TrainingClassifier,
)
from tests.coach.factories import make_activity


def _classify(distance_km: float) -> str:

    return TrainingClassifier.classify(
        make_activity(distance=distance_km * 1000),
    )


def test_long_run_starts_at_ten_km():
    """Longão segue o mesmo piso de 10km do resto do sistema."""

    assert _classify(10.0) == "LONG_RUN"
    assert _classify(15.0) == "LONG_RUN"


def test_below_ten_km_is_never_long_run():
    """9.9km não é longão — alinhado ao padrão."""

    assert _classify(9.9) == "RODAGEM"


def test_mid_distance_is_rodagem_not_easy_or_tempo():
    """Sem pace, distância média é rodagem de base — nem leve, nem tempo."""

    assert _classify(7.0) == "RODAGEM"
    assert _classify(8.5) == "RODAGEM"


def test_short_distance_is_recovery():

    assert _classify(6.9) == "RECOVERY"
    assert _classify(3.0) == "RECOVERY"
