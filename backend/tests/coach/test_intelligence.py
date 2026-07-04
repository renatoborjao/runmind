from app.application.coach.intelligence.distance_intelligence import (
    DistanceIntelligence,
)
from app.application.coach.intelligence.history_intelligence import (
    HistoryIntelligence,
)
from app.application.coach.intelligence.injury_intelligence import (
    InjuryIntelligence,
)
from app.application.coach.intelligence.intensity_intelligence import (
    IntensityIntelligence,
)
from app.application.coach.intelligence.performance_intelligence import (
    PerformanceIntelligence,
)
from app.application.coach.intelligence.planning_intelligence import (
    PlanningIntelligence,
)
from app.application.coach.intelligence.recovery_intelligence import (
    RecoveryIntelligence,
)
from app.application.coach.intelligence.type_match_intelligence import (
    TypeMatchIntelligence,
)
from app.application.coach.signals.codes import (
    ConsistencyLevel,
    DistanceStatus,
    FatigueLevel,
    InjuryStatus,
    IntensityLevel,
    PaceEffortLevel,
    RecoveryStatus,
    TypeMatchStatus,
    WeeklyVolumeStatus,
)
from tests.coach.factories import (
    make_activity,
    make_context,
    make_enriched_activity,
    make_planned_session,
)

# ==========================================================
# DistanceIntelligence
# ==========================================================

def test_distance_unknown_when_no_plan():

    context = make_context(
        planned=make_planned_session(planned_distance_km=0),
    )

    finding = DistanceIntelligence.process(context)

    assert finding.code == DistanceStatus.UNKNOWN.value


def test_distance_ok_at_exactly_10_percent_above():

    context = make_context(
        planned=make_planned_session(planned_distance_km=10.0),
        executed=make_enriched_activity(
            activity=make_activity(distance=11000.0),
        ),
    )

    finding = DistanceIntelligence.process(context)

    assert finding.code == DistanceStatus.OK.value


def test_distance_above_when_over_10_percent():

    context = make_context(
        planned=make_planned_session(planned_distance_km=10.0),
        executed=make_enriched_activity(
            activity=make_activity(distance=11010.0),
        ),
    )

    finding = DistanceIntelligence.process(context)

    assert finding.code == DistanceStatus.ABOVE.value


def test_distance_ok_at_exactly_10_percent_below():

    context = make_context(
        planned=make_planned_session(planned_distance_km=10.0),
        executed=make_enriched_activity(
            activity=make_activity(distance=9000.0),
        ),
    )

    finding = DistanceIntelligence.process(context)

    assert finding.code == DistanceStatus.OK.value


def test_distance_below_when_under_10_percent():

    context = make_context(
        planned=make_planned_session(planned_distance_km=10.0),
        executed=make_enriched_activity(
            activity=make_activity(distance=8990.0),
        ),
    )

    finding = DistanceIntelligence.process(context)

    assert finding.code == DistanceStatus.BELOW.value


# ==========================================================
# TypeMatchIntelligence
# ==========================================================

def test_type_match_when_codes_are_equal():

    context = make_context(
        planned=make_planned_session(workout_type="EASY"),
        executed=make_enriched_activity(training_type="EASY"),
    )

    finding = TypeMatchIntelligence.process(context)

    assert finding.code == TypeMatchStatus.MATCH.value


def test_progression_matches_easy_execution():

    context = make_context(
        planned=make_planned_session(workout_type="PROGRESSION"),
        executed=make_enriched_activity(training_type="EASY"),
    )

    finding = TypeMatchIntelligence.process(context)

    assert finding.code == TypeMatchStatus.MATCH.value


def test_type_mismatch_when_types_diverge():

    context = make_context(
        planned=make_planned_session(workout_type="VO2"),
        executed=make_enriched_activity(training_type="LONG_RUN"),
    )

    finding = TypeMatchIntelligence.process(context)

    assert finding.code == TypeMatchStatus.MISMATCH.value


# ==========================================================
# IntensityIntelligence
# ==========================================================

def test_intensity_levels():

    cases = {
        "VERY_HIGH": IntensityLevel.VERY_HIGH.value,
        "HIGH": IntensityLevel.HIGH.value,
        "MEDIUM": IntensityLevel.MEDIUM.value,
        "LOW": IntensityLevel.LOW.value,
        "ANYTHING_ELSE": IntensityLevel.LOW.value,
    }

    for intensity, expected_code in cases.items():

        context = make_context(
            executed=make_enriched_activity(intensity=intensity),
        )

        finding = IntensityIntelligence.process(context)

        assert finding.code == expected_code


# ==========================================================
# PerformanceIntelligence (pace_effort)
# ==========================================================

def test_pace_effort_boundaries():

    cases = {
        4.30: PaceEffortLevel.VERY_FAST.value,
        4.31: PaceEffortLevel.FAST.value,
        5.20: PaceEffortLevel.FAST.value,
        5.21: PaceEffortLevel.MODERATE.value,
        6.20: PaceEffortLevel.MODERATE.value,
        6.21: PaceEffortLevel.EASY.value,
    }

    for pace, expected_code in cases.items():

        context = make_context(
            executed=make_enriched_activity(pace_min_km=pace),
        )

        finding = PerformanceIntelligence.process(context)

        assert finding.code == expected_code


# ==========================================================
# RecoveryIntelligence
# ==========================================================

def test_recovery_hours_boundaries():

    cases = {
        48: RecoveryStatus.LONG.value,
        47: RecoveryStatus.MODERATE.value,
        36: RecoveryStatus.MODERATE.value,
        35: RecoveryStatus.SHORT.value,
    }

    for hours, expected_code in cases.items():

        context = make_context(recovery_hours=hours)

        finding = RecoveryIntelligence.process_recovery(context)

        assert finding.code == expected_code


def test_fatigue_boundaries():

    context_high = make_context(fatigue=80)
    context_moderate_edge = make_context(fatigue=79)
    context_moderate = make_context(fatigue=50)
    context_none = make_context(fatigue=49)

    assert RecoveryIntelligence.process_fatigue(
        context_high,
    ).code == FatigueLevel.HIGH.value

    assert RecoveryIntelligence.process_fatigue(
        context_moderate_edge,
    ).code == FatigueLevel.MODERATE.value

    assert RecoveryIntelligence.process_fatigue(
        context_moderate,
    ).code == FatigueLevel.MODERATE.value

    assert RecoveryIntelligence.process_fatigue(
        context_none,
    ) is None


# ==========================================================
# HistoryIntelligence
# ==========================================================

def test_consistency_boundaries():

    cases = {
        90: ConsistencyLevel.EXCELLENT.value,
        89: ConsistencyLevel.GOOD.value,
        75: ConsistencyLevel.GOOD.value,
        74: ConsistencyLevel.FAIR.value,
        50: ConsistencyLevel.FAIR.value,
        49: ConsistencyLevel.LOW.value,
    }

    for consistency, expected_code in cases.items():

        context = make_context(consistency=consistency)

        finding = HistoryIntelligence.process_consistency(context)

        assert finding.code == expected_code


def test_weekly_volume_no_goal():

    context = make_context(weekly_goal=0, weekly_volume=0)

    finding = HistoryIntelligence.process_weekly_volume(context)

    assert finding.code == WeeklyVolumeStatus.NO_GOAL.value


def test_weekly_volume_progress_boundaries():

    cases = {
        10.0: WeeklyVolumeStatus.COMPLETED.value,
        9.9: WeeklyVolumeStatus.NEAR_COMPLETE.value,
        8.0: WeeklyVolumeStatus.NEAR_COMPLETE.value,
        7.9: WeeklyVolumeStatus.IN_PROGRESS.value,
    }

    for weekly_volume, expected_code in cases.items():

        context = make_context(
            weekly_goal=10.0,
            weekly_volume=weekly_volume,
        )

        finding = HistoryIntelligence.process_weekly_volume(context)

        assert finding.code == expected_code


# ==========================================================
# PlanningIntelligence
# ==========================================================

def test_planning_intelligence_maps_next_planned_session():

    context = make_context(
        next_planned=make_planned_session(
            day="Thursday",
            workout_type="Intervalado",
            objective="Velocidade",
            planned_distance_km=8.0,
            target_pace_min="4:30",
            target_pace_max="4:50",
            notes="Levar tênis de pista",
        ),
    )

    next_training = PlanningIntelligence.process(context)

    assert next_training.day == "Thursday"
    assert next_training.workout_type == "Intervalado"
    assert next_training.objective == "Velocidade"
    assert next_training.distance_km == 8.0
    assert next_training.pace == "4:30 - 4:50"
    assert next_training.notes == "Levar tênis de pista"


def test_planning_intelligence_defaults_pace_when_absent():

    context = make_context(
        next_planned=make_planned_session(
            target_pace_min=None,
            target_pace_max=None,
        ),
    )

    next_training = PlanningIntelligence.process(context)

    assert next_training.pace == "-"


def test_planning_intelligence_returns_none_without_upcoming_session():

    context = make_context(next_planned=None)

    assert PlanningIntelligence.process(context) is None


# ==========================================================
# InjuryIntelligence
# ==========================================================

def test_injury_returns_none_when_no_injuries():

    context = make_context(injuries=[])

    assert InjuryIntelligence.process(context) is None


def test_injury_active_when_injuries_registered():

    context = make_context(
        injuries=["canelite", "fascite plantar"],
    )

    finding = InjuryIntelligence.process(context)

    assert finding.code == InjuryStatus.ACTIVE.value
    assert finding.params["injuries"] == "canelite, fascite plantar"
