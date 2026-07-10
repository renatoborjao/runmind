from app.application.garmin.garmin_workout_builder import (
    GarminWorkoutBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import WorkoutStep


def _session(**overrides) -> PlannedSession:

    defaults = dict(
        day="Saturday",
        workout_type="Longão",
        objective="",
        planned_distance_km=12.2,
        planned_duration_minutes=None,
        target_pace_min="6:32",
        target_pace_max="7:08",
    )

    defaults.update(overrides)

    return PlannedSession(**defaults)


def _steps(workout) -> list:

    return workout.to_dict()["workoutSegments"][0]["workoutSteps"]


# ---------------- fallback (sem steps estruturados) ----------------


def test_fallback_single_distance_pace_step():

    step = _steps(GarminWorkoutBuilder.build(_session(), "Longão"))[0]

    assert step["endConditionValue"] == 12200.0
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    # 6:32=2.551 (rápido), 7:08=2.336 (lento)
    assert step["targetValueOne"] == 2.336
    assert step["targetValueTwo"] == 2.551


def test_fallback_no_pace_is_no_target():

    step = _steps(
        GarminWorkoutBuilder.build(
            _session(target_pace_min=None, target_pace_max=None), "Rodagem"
        )
    )[0]

    assert step["targetType"]["workoutTargetTypeKey"] == "no.target"


# ---------------- treino estruturado (steps da IA) ----------------


def _interval_session() -> PlannedSession:
    """6x800 com aquecimento, recuperação e desaquecimento."""

    return _session(
        workout_type="Velocidade",
        planned_distance_km=9.0,
        steps=[
            WorkoutStep(kind="warmup", distance_m=2000,
                        pace_min="6:30", pace_max="7:00"),
            WorkoutStep(
                kind="repeat",
                reps=6,
                steps=[
                    WorkoutStep(kind="interval", distance_m=800,
                                pace_min="4:45", pace_max="4:50"),
                    WorkoutStep(kind="recovery", distance_m=400),
                ],
            ),
            WorkoutStep(kind="cooldown", distance_m=1500,
                        pace_min="6:30", pace_max="7:00"),
        ],
    )


def test_structured_interval_has_warmup_repeat_cooldown():

    steps = _steps(GarminWorkoutBuilder.build(_interval_session(), "Tiros"))

    # warmup, repeat group, cooldown
    assert steps[0]["stepType"]["stepTypeKey"] == "warmup"
    assert steps[1]["type"] == "RepeatGroupDTO"
    assert steps[-1]["stepType"]["stepTypeKey"] == "cooldown"


def test_repeat_group_has_reps_and_children():

    repeat = _steps(
        GarminWorkoutBuilder.build(_interval_session(), "Tiros")
    )[1]

    assert repeat["numberOfIterations"] == 6

    children = repeat["workoutSteps"]
    assert children[0]["stepType"]["stepTypeKey"] == "interval"
    assert children[0]["endConditionValue"] == 800.0
    assert children[0]["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert children[1]["stepType"]["stepTypeKey"] == "recovery"
    assert children[1]["targetType"]["workoutTargetTypeKey"] == "no.target"


def test_step_order_is_sequential_across_repeat():
    """stepOrder tem que ser único e sequencial no treino todo, inclusive
    dentro do grupo de repetição."""

    steps = _steps(GarminWorkoutBuilder.build(_interval_session(), "Tiros"))

    orders = []

    def collect(items):
        for it in items:
            orders.append(it["stepOrder"])
            if it.get("workoutSteps"):
                collect(it["workoutSteps"])

    collect(steps)

    # warmup=1, repeat=2, interval=3, recovery=4, cooldown=5
    assert orders == [1, 2, 3, 4, 5]


def test_duration_based_step_uses_time_condition():

    session = _session(
        steps=[
            WorkoutStep(kind="recovery", duration_sec=120),
        ],
    )

    step = _steps(GarminWorkoutBuilder.build(session, "Regen"))[0]

    assert step["endCondition"]["conditionTypeKey"] == "time"
    assert step["endConditionValue"] == 120.0


def test_open_step_uses_lap_button():

    session = _session(steps=[WorkoutStep(kind="run")])

    step = _steps(GarminWorkoutBuilder.build(session, "Livre"))[0]

    assert step["endCondition"]["conditionTypeKey"] == "lap.button"


def test_hr_target_step():

    session = _session(
        steps=[WorkoutStep(kind="run", distance_m=5000, hr_min=140, hr_max=150)]
    )

    step = _steps(GarminWorkoutBuilder.build(session, "Z2"))[0]

    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["targetValueOne"] == 140.0
    assert step["targetValueTwo"] == 150.0


def test_walk_session_builds_walking_workout():

    workout = GarminWorkoutBuilder.build(
        _session(kind="walk", workout_type="Caminhada"), "Caminhada"
    )

    assert workout.to_dict()["sportType"]["sportTypeKey"] == "walking"
