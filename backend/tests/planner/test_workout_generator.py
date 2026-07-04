from app.application.workouts.generator import WorkoutGenerator


def test_generate_tempo():

    s = WorkoutGenerator.generate_tempo(6.0)

    assert s.workout_type == "TEMPO"
    assert s.planned_distance_km == 6.0


def test_generate_fartlek():

    s = WorkoutGenerator.generate_fartlek(5.0)

    assert s.workout_type == "FARTLEK"


def test_generate_recovery():

    s = WorkoutGenerator.generate_recovery(4.0)

    assert s.workout_type == "RECOVERY"


def test_dispatcher_routes_by_type():

    assert WorkoutGenerator.generate("TEMPO", 6.0).workout_type == "TEMPO"
    assert WorkoutGenerator.generate("FARTLEK", 5.0).workout_type == "FARTLEK"
    assert WorkoutGenerator.generate("VO2", 6.0).workout_type == "VO2"
    assert WorkoutGenerator.generate("LONG_RUN", 12.0).workout_type == "LONG_RUN"


def test_dispatcher_unknown_falls_back_to_easy():

    assert WorkoutGenerator.generate("BANANA", 5.0).workout_type == "EASY"
