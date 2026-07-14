import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.garmin.garmin_activity_poller import (
    GarminActivityPoller,
)
from tests.coach.factories import make_activity

MODULE = "app.application.garmin.garmin_activity_poller"


def _garmin_with_activities(ids):

    garmin = MagicMock()
    garmin.get_activities.return_value = [
        {"activityId": i} for i in ids
    ]
    return garmin


def test_poll_one_seeds_when_not_seeded_and_does_not_analyze():
    """Atleta sem marcador (recém-conectado sem seed): só semeia, não
    analisa nada — nada de feedback do histórico antigo."""

    marker = MagicMock()
    marker.exists.return_value = False

    with (
        patch(f"{MODULE}._seeded_marker", return_value=marker),
        patch(f"{MODULE}.GarminActivityPoller.seed_history") as seed,
        patch(
            f"{MODULE}.GarminActivityPoller._analyze", new_callable=AsyncMock
        ) as analyze,
    ):

        asyncio.run(GarminActivityPoller.poll_one("renato2"))

        seed.assert_called_once_with("renato2")
        analyze.assert_not_awaited()


def test_poll_one_analyzes_only_new_activities():
    """Semeado: analisa só o que ainda não passou pelo guard (dedup)."""

    marker = MagicMock()
    marker.exists.return_value = True

    guard = MagicMock()
    # id 200 é novo (True), id 100 já visto (False)
    guard.check_and_mark.side_effect = lambda aid: aid == 200

    with (
        patch(f"{MODULE}._seeded_marker", return_value=marker),
        patch(f"{MODULE}.GarminClient") as client,
        patch(f"{MODULE}.ProcessedActivityGuard", return_value=guard),
        patch(
            f"{MODULE}.GarminActivityPoller._analyze", new_callable=AsyncMock
        ) as analyze,
    ):

        client.connect.return_value = _garmin_with_activities([200, 100])

        asyncio.run(GarminActivityPoller.poll_one("renato2"))

        analyze.assert_awaited_once_with("renato2", 200)


def test_seed_history_marks_without_analyzing():

    guard = MagicMock()

    marker = MagicMock()

    with (
        patch(f"{MODULE}.GarminClient") as client,
        patch(f"{MODULE}.ProcessedActivityGuard", return_value=guard),
        patch(f"{MODULE}._seeded_marker", return_value=marker),
    ):

        client.is_connected.return_value = True
        client.connect.return_value = _garmin_with_activities([1, 2, 3])

        GarminActivityPoller.seed_history("renato2")

        # marcou os 3 e gravou o marcador
        assert guard.check_and_mark.call_count == 3
        marker.write_text.assert_called_once()


def test_analyze_skips_activity_without_distance():
    """Corrida sem distância (esteira/HIIT sem sensor): pula sem crashar nem
    enviar — senão o enricher dividiria por zero (bug do Mauricio)."""

    with (
        patch(f"{MODULE}.GarminActivitySource") as source,
        patch(f"{MODULE}.TrainingCompletedEvent") as event,
    ):

        source.fetch.return_value = make_activity(sport="Run", distance=0.0)
        event.execute = AsyncMock()

        asyncio.run(GarminActivityPoller._analyze("mauricio", 999))

        event.execute.assert_not_awaited()


def test_analyze_processes_activity_with_distance():
    """Controle: corrida com distância segue pra análise normalmente."""

    with (
        patch(f"{MODULE}.GarminActivitySource") as source,
        patch(f"{MODULE}.TrainingCompletedEvent") as event,
    ):

        source.fetch.return_value = make_activity(sport="Run", distance=8000.0)
        event.execute = AsyncMock()

        asyncio.run(GarminActivityPoller._analyze("renato2", 999))

        event.execute.assert_awaited_once()


def test_seed_history_skips_when_not_connected():

    with patch(f"{MODULE}.GarminClient") as client:

        client.is_connected.return_value = False

        # não levanta, não faz nada
        GarminActivityPoller.seed_history("renato2")

        client.connect.assert_not_called()
