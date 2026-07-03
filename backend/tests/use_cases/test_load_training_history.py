import asyncio
from unittest.mock import AsyncMock, patch

from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from tests.coach.factories import make_activity

MODULE = "app.application.use_cases.load_training_history"


def test_history_keeps_only_foot_sports():

    activities = [
        make_activity(id=1, sport="Run"),
        make_activity(id=2, sport="Ride"),
        make_activity(id=3, sport="Walk"),
        make_activity(id=4, sport="Swim"),
        make_activity(id=5, sport="WeightTraining"),
        make_activity(id=6, sport="VirtualRun"),
    ]

    with (
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.ActivityArchiveRepository"),
    ):

        mock_token_store.return_value.load.return_value = {"access_token": "x"}

        mock_client = mock_client_cls.return_value

        mock_client.get_last_activities = AsyncMock(
            return_value=activities,
        )

        history = asyncio.run(
            LoadTrainingHistory.execute(profile="renato"),
        )

    assert [activity.id for activity in history.activities] == [1, 3, 6]


def test_profile_without_strava_tokens_gets_empty_history():

    with (
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
    ):

        mock_token_store.return_value.load.return_value = None

        history = asyncio.run(
            LoadTrainingHistory.execute(profile="beatriz"),
        )

    assert history.activities == []

    mock_client_cls.assert_not_called()


def test_direct_activity_bypasses_strava():

    activity = make_activity(id=7, sport="Run")

    with patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive:

        history = asyncio.run(
            LoadTrainingHistory.execute(activity=activity),
        )

        # o caminho direto (webhook) também alimenta o arquivo
        mock_archive.return_value.upsert_many.assert_called_once()

    assert history.activities == [activity]


def test_fetched_activities_are_archived():

    activities = [
        make_activity(id=1, sport="Run"),
        make_activity(id=2, sport="Ride"),  # filtrada do histórico
    ]

    with (
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive_cls,
    ):

        mock_token_store.return_value.load.return_value = {"t": 1}

        mock_client = mock_client_cls.return_value
        mock_client.get_last_activities = AsyncMock(
            return_value=activities,
        )

        asyncio.run(LoadTrainingHistory.execute(profile="renato"))

        archived = mock_archive_cls.return_value.upsert_many.call_args
        # só o que passou no filtro de esporte é arquivado
        assert [a.id for a in archived.args[1]] == [1]


def test_archive_failure_does_not_break_history_load():

    with (
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive_cls,
    ):

        mock_token_store.return_value.load.return_value = {"t": 1}

        mock_client = mock_client_cls.return_value
        mock_client.get_last_activities = AsyncMock(
            return_value=[make_activity(id=1, sport="Run")],
        )

        mock_archive_cls.return_value.upsert_many.side_effect = (
            OSError("disco cheio")
        )

        history = asyncio.run(
            LoadTrainingHistory.execute(profile="renato"),
        )

        assert len(history.activities) == 1
