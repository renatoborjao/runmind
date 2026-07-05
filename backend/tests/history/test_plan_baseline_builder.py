from app.application.history.plan_baseline_builder import (
    PlanBaselineBuilder,
)


def test_from_sessions_builds_the_retrato():

    sessions = [
        {"day": "Monday", "distance_km": 7.2},
        {"day": "Tuesday", "distance_km": 5.0},
        {"day": "Thursday", "distance_km": 9.0},
        {"day": "Saturday", "distance_km": 7.0},
        {"day": "Sunday", "distance_km": 12.0},
    ]

    seed = PlanBaselineBuilder.from_sessions(sessions)

    assert seed == {
        "weekly_km": 40.2,
        "runs_per_week": 5,
        "typical_km": 7.2,   # mediana de [5, 7, 7.2, 9, 12]
        "longest_km": 12.0,
    }


def test_ignores_sessions_without_distance():

    sessions = [
        {"day": "Wednesday", "distance_km": None},   # musculação
        {"day": "Friday", "workout_type": "Musculação"},
        {"day": "Tuesday", "distance_km": 5.0},
    ]

    seed = PlanBaselineBuilder.from_sessions(sessions)

    assert seed == {
        "weekly_km": 5.0,
        "runs_per_week": 1,
        "typical_km": 5.0,
        "longest_km": 5.0,
    }


def test_no_running_sessions_returns_none():

    assert PlanBaselineBuilder.from_sessions(
        [{"day": "Monday", "distance_km": None}]
    ) is None
