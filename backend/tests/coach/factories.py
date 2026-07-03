from __future__ import annotations

from datetime import datetime

from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.domain.entities.activity import (
    Activity,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)
from app.domain.entities.runner_profile import (
    RunnerProfile,
)


def make_runner(**overrides) -> RunnerProfile:

    defaults = dict(
        id="runner-1",
        name="Renato",
        age=30,
        weight=70.0,
        height=175.0,
        phone="5511999999999",
        goal="10k",
        weekly_training_days=4,
    )

    defaults.update(overrides)

    return RunnerProfile(**defaults)


def make_activity(**overrides) -> Activity:

    defaults = dict(
        id=1,
        name="Corrida",
        sport="Run",
        start_date=datetime(2026, 7, 1, 7, 0, 0),
        timezone="America/Sao_Paulo",
        distance=10000.0,
        moving_time=3000,
        elapsed_time=3100,
        average_speed=3.33,
        max_speed=4.5,
        average_heartrate=150.0,
        max_heartrate=175.0,
        elevation_gain=50.0,
        elevation_high=None,
        elevation_low=None,
        start_latitude=None,
        start_longitude=None,
        end_latitude=None,
        end_longitude=None,
        kudos=0,
        comments=0,
        suffer_score=None,
        raw={},
    )

    defaults.update(overrides)

    return Activity(**defaults)


def make_planned_session(**overrides) -> PlannedSession:

    defaults = dict(
        day="Tuesday",
        workout_type="Rodagem Leve",
        objective="Base aeróbica",
        planned_distance_km=10.0,
        planned_duration_minutes=60,
        target_pace_min=None,
        target_pace_max=None,
        notes="",
    )

    defaults.update(overrides)

    return PlannedSession(**defaults)


def make_enriched_activity(**overrides) -> EnrichedActivity:

    defaults = dict(
        activity=make_activity(),
        pace_min_km=5.0,
        training_type="RODAGEM",
        intensity="MEDIUM",
        estimated_zone="Z2",
        training_load=50.0,
        fatigue_score=40.0,
        recovery_hours=24,
        efficiency_score=80.0,
        indoor=False,
    )

    defaults.update(overrides)

    return EnrichedActivity(**defaults)


def make_context(**overrides) -> CoachContext:

    defaults = dict(
        runner=make_runner(),
        planned=make_planned_session(),
        executed=make_enriched_activity(),
        weekly_volume=0,
        weekly_goal=0,
        consistency=0,
        fatigue=0,
        recovery_hours=0,
    )

    defaults.update(overrides)

    return CoachContext(**defaults)
