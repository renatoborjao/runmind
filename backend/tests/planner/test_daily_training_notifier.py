import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner

MODULE = "app.application.planner.daily_training_notifier"

FORECAST = {
    "temp_max": 33.0, "temp_min": 22.0,
    "feels_max": 35.0, "rain_prob": 10,
}


def _run_notify_one(history, forecast, session_message="🏃 Treino de hoje"):

    sent = {}

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_history,
        patch(f"{MODULE}.OpenMeteoClient") as mock_weather,
        patch(f"{MODULE}.NotificationService") as mock_notifier,
    ):

        mock_provider.for_profile = AsyncMock(
            return_value=(make_runner(name="Mauricio"), MagicMock()),
        )

        mock_formatter.today_session_message.return_value = session_message

        mock_history.execute = AsyncMock(return_value=history)

        mock_weather.forecast_today = AsyncMock(return_value=forecast)

        async def _capture(runner, message):
            sent["message"] = message

        mock_notifier.send = AsyncMock(side_effect=_capture)

        asyncio.run(DailyTrainingNotifier._notify_one("mauricio"))

    return sent


def _outdoor(day, lat, lng):

    return make_activity(
        start_date=datetime(2026, 7, day, 7, 0, 0),
        start_latitude=lat,
        start_longitude=lng,
    )


def test_reminder_appends_weather_line():

    history = TrainingHistory(activities=[_outdoor(3, -23.5, -46.6)])

    sent = _run_notify_one(history, FORECAST)

    assert "🏃 Treino de hoje" in sent["message"]
    assert "Clima hoje" in sent["message"]
    assert "33°C" in sent["message"]


def test_reminder_without_gps_has_no_weather_line():

    # só treino de esteira (sem coordenadas) -> sem linha de clima
    treadmill = make_activity(start_latitude=None, start_longitude=None)

    sent = _run_notify_one(
        TrainingHistory(activities=[treadmill]),
        FORECAST,
    )

    assert "🏃 Treino de hoje" in sent["message"]
    assert "Clima hoje" not in sent["message"]


def test_rest_day_sends_nothing():

    sent = _run_notify_one(
        TrainingHistory(activities=[]),
        FORECAST,
        session_message=None,  # dia de descanso
    )

    assert sent == {}


def test_latest_coords_picks_most_recent_outdoor():

    history = TrainingHistory(activities=[
        _outdoor(1, -20.0, -40.0),
        make_activity(start_date=datetime(2026, 7, 5, 7, 0),
                      start_latitude=None, start_longitude=None),
        _outdoor(4, -23.5, -46.6),  # mais recente com GPS
    ])

    assert DailyTrainingNotifier._latest_coords(history) == (-23.5, -46.6)


def test_latest_coords_none_without_gps():

    history = TrainingHistory(activities=[
        make_activity(start_latitude=None, start_longitude=None),
    ])

    assert DailyTrainingNotifier._latest_coords(history) is None
