from datetime import datetime
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.form_coach_detector import (
    FormCoachDetector,
)
from app.domain.entities.activity import Activity
from app.domain.entities.enriched_activity import EnrichedActivity

MODULE = "app.application.coach.intelligence.form_coach_detector"


def _activity(km: float = 6.0, sport: str = "Run") -> Activity:

    return Activity(
        id=1, name="run", sport=sport,
        start_date=datetime(2026, 8, 1, 7, 0),
        timezone="America/Sao_Paulo",
        distance=km * 1000, moving_time=2160, elapsed_time=2160,
        average_speed=2.78, max_speed=3.0,
        average_heartrate=150.0, max_heartrate=170.0,
        elevation_gain=0.0, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None, raw={},
    )


def _enriched(cadence, pace=6.0, km=6.0, sport="Run") -> EnrichedActivity:

    structure = MagicMock()
    structure.cadence_spm = cadence

    return EnrichedActivity(
        activity=_activity(km, sport),
        pace_min_km=pace,
        training_type="Rodagem",
        intensity="easy",
        estimated_zone="Z2",
        training_load=50.0,
        fatigue_score=1.0,
        recovery_hours=24,
        efficiency_score=1.0,
        indoor=False,
        structure=structure,
    )


def _runner():

    r = MagicMock()
    r.name = "Renato"
    return r


def test_low_cadence_sends_tip_once():

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.return_value = False

        tip = FormCoachDetector.after_feedback(
            "renato", _runner(), _enriched(cadence=158),
        )

    assert tip is not None
    assert "158" in tip
    assert "170-175" in tip
    guard.mark.assert_called_once_with("form_cadence", "renato", "v1")


def test_already_sent_does_not_repeat():

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.return_value = True

        tip = FormCoachDetector.after_feedback(
            "renato", _runner(), _enriched(cadence=158),
        )

    assert tip is None
    guard.mark.assert_not_called()


def test_good_cadence_no_tip():

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.return_value = False

        tip = FormCoachDetector.after_feedback(
            "renato", _runner(), _enriched(cadence=174),
        )

    assert tip is None


def test_slow_jog_pace_does_not_coach_cadence():
    """Em ritmo de trote/caminhada, cadência baixa é natural — não coacha."""

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.return_value = False

        tip = FormCoachDetector.after_feedback(
            "renato", _runner(), _enriched(cadence=155, pace=8.2),
        )

    assert tip is None


def test_no_structure_no_tip():

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.return_value = False

        enriched = _enriched(cadence=155)
        enriched.structure = None

        tip = FormCoachDetector.after_feedback("renato", _runner(), enriched)

    assert tip is None
