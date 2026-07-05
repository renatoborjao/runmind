from app.application.planner.engines.run_walk_engine import RunWalkEngine
from tests.coach.factories import make_runner

DAYS5 = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_alternates_run_walk_and_walk_capped_at_three():

    runner = make_runner(
        weight=138.0, height=1.88, mobility="run_walker",
    )

    sessions = RunWalkEngine.build(DAYS5, 1, runner)

    types = [s.workout_type for s in sessions]

    # dia sim/dia não pra run/walk (máx 3), o resto caminhada
    assert types == ["RUN_WALK", "WALK", "RUN_WALK", "WALK", "RUN_WALK"]


def test_few_days_are_all_run_walk():

    runner = make_runner(mobility="walker")

    sessions = RunWalkEngine.build(["Tuesday", "Thursday"], 1, runner)

    assert [s.workout_type for s in sessions] == ["RUN_WALK", "RUN_WALK"]


def test_run_walk_is_time_based_not_distance():

    runner = make_runner(mobility="run_walker")

    session = RunWalkEngine.build(["Monday"], 1, runner)[0]

    assert session.planned_distance_km is None

    # 5 aquec + 5 desaquec + 5x(30s trote + 180s caminhada)=17.5min -> 28
    assert session.planned_duration_minutes == 28

    assert session.intervals == {
        "warmup_min": 5,
        "trot_sec": 30,
        "walk_sec": 180,
        "reps": 5,
        "cooldown_min": 5,
    }


def test_progression_grows_trot_and_reps_by_week():

    runner = make_runner(mobility="run_walker")

    week3 = RunWalkEngine.build(["Monday"], 3, runner)[0].intervals

    assert week3["trot_sec"] == 60   # 30 + 2*15
    assert week3["reps"] == 7        # 5 + 2


def test_trot_never_exceeds_declared_capacity():

    # aguenta só 1 min corrido: semana 5 (que daria 90s) fica travada em 60s
    runner = make_runner(
        mobility="run_walker", continuous_run_minutes=1.0,
    )

    session = RunWalkEngine.build(["Monday"], 5, runner)[0]

    assert session.intervals["trot_sec"] == 60


def test_walk_session_uses_declared_walk_pace():

    runner = make_runner(
        mobility="walker", walk_pace_min_km=round(60 / 5.5, 2),
    )

    walk = next(
        s
        for s in RunWalkEngine.build(DAYS5, 1, runner)
        if s.workout_type == "WALK"
    )

    assert walk.planned_duration_minutes == 25
    assert walk.target_pace_min == "10:55"  # 5,5 km/h
