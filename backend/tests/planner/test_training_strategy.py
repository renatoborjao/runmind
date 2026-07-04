from app.application.planner.strategy.training_strategy import (
    TrainingStrategy,
)
from app.domain.entities.training_assessment import TrainingAssessment


def _assessment() -> TrainingAssessment:

    return TrainingAssessment(
        level="Intermediate",
        current_weekly_volume=30.0,
        recommended_weekly_volume=30.0,
        consistency=80.0,
        longest_run=12.0,
        available_training_days=3,
        goal="10k",
        observations=[],
    )


def test_base_and_build_carry_full_volume():

    assert TrainingStrategy.build(_assessment(), "BASE")["weekly_volume"] == 30.0
    assert TrainingStrategy.build(_assessment(), "BUILD")["weekly_volume"] == 30.0


def test_peak_trims_volume():

    assert TrainingStrategy.build(_assessment(), "PEAK")["weekly_volume"] == 27.0


def test_taper_reduces_volume():

    assert TrainingStrategy.build(_assessment(), "TAPER")["weekly_volume"] == 18.0


def test_deload_cuts_twenty_percent_on_build():

    strategy = TrainingStrategy.build(_assessment(), "BUILD", is_deload=True)

    assert strategy["weekly_volume"] == 24.0  # 30 * 0.8


def test_deload_applies_over_base_too():

    strategy = TrainingStrategy.build(_assessment(), "BASE", is_deload=True)

    assert strategy["weekly_volume"] == 24.0
