from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from tests.coach.factories import make_activity

MODULE = "app.presentation.api.v1.webhooks"

PAYLOAD = {
    "object_type": "activity",
    "object_id": 123,
    "owner_id": 111,
}


def _post_webhook(sport: str):

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
    ):

        mock_resolver.resolve.return_value = "renato"

        mock_client = mock_client_cls.return_value
        mock_client.get_activity = AsyncMock(
            return_value=make_activity(sport=sport),
        )

        mock_event.execute = AsyncMock()

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json=PAYLOAD,
        )

        return response.json(), mock_event


def test_ride_is_ignored_and_does_not_trigger_feedback():

    body, mock_event = _post_webhook("Ride")

    assert body["ignored"] is True
    assert "Ride" in body["reason"]

    mock_event.execute.assert_not_awaited()


def test_run_triggers_training_completed_event():

    body, mock_event = _post_webhook("Run")

    assert body.get("success") is True

    mock_event.execute.assert_awaited_once()
