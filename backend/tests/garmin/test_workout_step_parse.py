from app.domain.entities.workout_step import parse_steps


def test_parses_distance_km_to_meters():

    steps = parse_steps([{"kind": "warmup", "distance_km": 2}])

    assert steps[0].distance_m == 2000.0


def test_parses_duration_min_to_seconds():

    steps = parse_steps([{"kind": "recovery", "duration_min": 2}])

    assert steps[0].duration_sec == 120


def test_parses_nested_repeat():

    steps = parse_steps(
        [
            {
                "kind": "repeat",
                "reps": 6,
                "steps": [
                    {"kind": "interval", "distance_m": 800,
                     "pace_min": "4:45", "pace_max": "4:50"},
                    {"kind": "recovery", "distance_m": 400},
                ],
            }
        ]
    )

    assert len(steps) == 1
    assert steps[0].is_repeat
    assert steps[0].reps == 6
    assert len(steps[0].steps) == 2
    assert steps[0].steps[0].pace_min == "4:45"


def test_repeat_without_children_is_dropped():

    assert parse_steps([{"kind": "repeat", "reps": 6, "steps": []}]) == []


def test_unknown_kind_is_dropped():

    assert parse_steps([{"kind": "musculacao", "duration_min": 30}]) == []


def test_garbage_is_ignored():

    assert parse_steps("nonsense") == []
    assert parse_steps([None, 42, {"no_kind": True}]) == []
