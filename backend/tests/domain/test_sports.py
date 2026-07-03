from app.domain.value_objects.sports import is_foot_sport


def test_running_walking_and_treadmill_are_supported():

    for sport in ("Run", "TrailRun", "VirtualRun", "Walk", "Hike"):

        assert is_foot_sport(sport)


def test_other_sports_are_not_supported():

    for sport in ("Ride", "VirtualRide", "Swim", "WeightTraining", "Yoga"):

        assert not is_foot_sport(sport)
