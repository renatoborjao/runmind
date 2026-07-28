from unittest.mock import MagicMock, patch

from app.application.garmin.garmin_activity_poller import GarminActivityPoller
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)

MOD = "app.application.garmin.garmin_activity_poller"


def _item(type_key, activity_id=100, duration=2700, avg_hr=120):

    return {
        "activityId": activity_id,
        "activityName": type_key,
        "activityType": {"typeKey": type_key},
        "startTimeLocal": "2026-07-20 06:30:00",
        "duration": duration,
        "averageHR": avg_hr,
    }


def test_summary_from_item_keeps_load_fields():

    activity = GarminActivitySource.summary_from_item(
        _item("strength_training", activity_id=9, duration=3000, avg_hr=110)
    )

    assert activity.id == 9
    assert activity.sport == "strength_training"   # typeKey cru, informativo
    assert activity.moving_time == 3000
    assert activity.average_heartrate == 110.0
    assert activity.distance == 0.0                # nunca é corrida


def test_capture_routes_non_foot_to_body_counter():

    with patch(f"{MOD}.CrossTrainingRepository") as repo_cls:

        repo = MagicMock()
        repo_cls.return_value = repo

        captured = GarminActivityPoller._capture_cross_training(
            "mauricio", _item("strength_training")
        )

        assert captured is True                    # para aqui, não analisa
        repo.upsert_many.assert_called_once()

        (_profile, activities), _ = repo.upsert_many.call_args
        assert activities[0].sport == "strength_training"


def test_capture_lets_running_through():

    with patch(f"{MOD}.CrossTrainingRepository") as repo_cls:

        repo = MagicMock()
        repo_cls.return_value = repo

        captured = GarminActivityPoller._capture_cross_training(
            "renato2", _item("running")
        )

        assert captured is False                   # corrida segue o fluxo normal
        repo.upsert_many.assert_not_called()


def test_capture_lets_unknown_type_through():

    # item sem activityType: NÃO arrisca desviar (pode ser corrida) — cai no
    # fluxo normal (_analyze deep-fetch decide)
    with patch(f"{MOD}.CrossTrainingRepository") as repo_cls:

        repo = MagicMock()
        repo_cls.return_value = repo

        captured = GarminActivityPoller._capture_cross_training(
            "renato2", {"activityId": 5, "duration": 1800}
        )

        assert captured is False
        repo.upsert_many.assert_not_called()


def test_capture_swim_is_body_counter():

    with patch(f"{MOD}.CrossTrainingRepository") as repo_cls:

        repo = MagicMock()
        repo_cls.return_value = repo

        assert GarminActivityPoller._capture_cross_training(
            "fernanda", _item("lap_swimming")
        ) is True
        repo.upsert_many.assert_called_once()
