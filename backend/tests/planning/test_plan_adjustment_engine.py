from datetime import date

from app.application.coach.planning.plan_adjustment_engine import (
    PlanAdjustmentEngine,
)
from app.application.coach.signals.coach_analysis import CoachAnalysis
from app.application.coach.signals.codes import (
    DistanceStatus,
    FatigueLevel,
    InjuryStatus,
    TypeMatchStatus,
)
from app.application.coach.signals.finding import Finding, FindingSeverity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

WEEK_START = date(2026, 7, 20)  # segunda-feira


def _session(day: str, distance: float = 8.0) -> PlannedSession:

    return PlannedSession(
        day=day,
        workout_type="Easy Run",
        objective="Base",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min="5:20",
        target_pace_max="5:50",
    )


def _plan(sessions: list[PlannedSession]) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Monday", "Wednesday", "Sunday"],
        week_start=WEEK_START,
        sessions=sessions,
    )


def _finding(code: str, params: dict | None = None) -> Finding:

    return Finding(
        code=code,
        severity=FindingSeverity.NEUTRAL,
        params=params or {},
    )


def _analysis(
    distance_code: str,
    fatigue_code: str | None,
    injured: bool = False,
) -> CoachAnalysis:

    fatigue = _finding(fatigue_code) if fatigue_code else None

    injury_risk = (
        _finding(InjuryStatus.ACTIVE.value) if injured else None
    )

    return CoachAnalysis(
        distance=_finding(
            distance_code,
            {"delta_percent": 35},
        ),
        type_match=_finding(TypeMatchStatus.MATCH.value),
        intensity=_finding("INTENSITY_HIGH"),
        pace_effort=_finding("PACE_FAST"),
        recovery=_finding("RECOVERY_MODERATE"),
        fatigue=fatigue,
        injury_risk=injury_risk,
    )


def test_adjusts_next_session_when_above_and_high_fatigue():

    monday = _session("Monday", distance=8.0)
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.ABOVE.value, FatigueLevel.HIGH.value),
    )

    assert note is not None
    assert wednesday.adjusted is True
    assert wednesday.planned_distance_km == 8.0  # 10.0 * 0.80
    assert wednesday.adjustment_reason == note

    # a sessão que já rodou não é tocada
    assert monday.adjusted is False
    assert monday.planned_distance_km == 8.0


def test_does_not_adjust_when_fatigue_is_moderate_not_high():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.ABOVE.value, FatigueLevel.MODERATE.value),
    )

    assert note is None
    assert wednesday.adjusted is False
    assert wednesday.planned_distance_km == 10.0


def test_does_not_adjust_when_no_fatigue_finding():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.ABOVE.value, None),
    )

    assert note is None
    assert wednesday.planned_distance_km == 10.0


def test_does_not_adjust_when_distance_is_below():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.BELOW.value, FatigueLevel.HIGH.value),
    )

    assert note is None
    assert wednesday.planned_distance_km == 10.0


def test_does_not_adjust_when_distance_is_ok():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.OK.value, FatigueLevel.HIGH.value),
    )

    assert note is None
    assert wednesday.planned_distance_km == 10.0


def test_adjusts_on_moderate_fatigue_when_injured():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(
            DistanceStatus.ABOVE.value,
            FatigueLevel.MODERATE.value,
            injured=True,
        ),
    )

    assert note is not None
    assert wednesday.adjusted is True
    assert wednesday.planned_distance_km == 8.0  # 10.0 * 0.80


def test_injury_alone_without_fatigue_does_not_adjust():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(
            DistanceStatus.ABOVE.value,
            None,
            injured=True,
        ),
    )

    assert note is None
    assert wednesday.planned_distance_km == 10.0


def test_external_plan_is_never_adjusted():

    monday = _session("Monday")
    wednesday = _session("Wednesday", distance=10.0)

    plan = _plan([monday, wednesday])
    plan.source = "externo"

    note = PlanAdjustmentEngine.adjust(
        plan,
        monday,
        _analysis(DistanceStatus.ABOVE.value, FatigueLevel.HIGH.value),
    )

    assert note is None
    assert wednesday.adjusted is False
    assert wednesday.planned_distance_km == 10.0


def test_returns_none_when_no_upcoming_session():

    sunday = _session("Sunday")  # última sessão da semana

    plan = _plan([sunday])

    note = PlanAdjustmentEngine.adjust(
        plan,
        sunday,
        _analysis(DistanceStatus.ABOVE.value, FatigueLevel.HIGH.value),
    )

    assert note is None
    assert sunday.adjusted is False
