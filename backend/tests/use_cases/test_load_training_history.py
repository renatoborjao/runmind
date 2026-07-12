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

        # arquivo vazio: histórico = só a atividade nova
        mock_archive.return_value.load_activities.return_value = []

        history = asyncio.run(
            LoadTrainingHistory.execute(activity=activity),
        )

        # o caminho direto (webhook) também alimenta o arquivo
        mock_archive.return_value.upsert_many.assert_called_once()

    assert history.activities == [activity]


def test_direct_activity_is_merged_with_archived_history():
    """Bug real (12/07): a análise pós-treino via só a corrida do dia e
    dizia "poucas semanas pra avaliar" mesmo com meses arquivados. Agora o
    arquivo entra junto, com a atividade nova à frente (newest-first) e sem
    duplicar a que acabou de chegar."""

    from datetime import datetime

    new = make_activity(
        id=7, sport="Run",
        start_date=datetime(2026, 7, 12, 7, 0, 0),
    )

    archived = [
        make_activity(id=5, start_date=datetime(2026, 7, 4, 7, 0, 0)),
        make_activity(id=6, start_date=datetime(2026, 7, 9, 7, 0, 0)),
        # a própria atividade nova, já arquivada em versão reduzida
        make_activity(id=7, start_date=datetime(2026, 7, 12, 7, 0, 0)),
    ]

    with patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive:

        mock_archive.return_value.load_activities.return_value = archived

        history = asyncio.run(
            LoadTrainingHistory.execute(activity=new),
        )

    # nova primeiro (mesmo objeto, dados completos), depois arquivo por data
    # decrescente; sem duplicar id=7
    assert [a.id for a in history.activities] == [7, 6, 5]
    assert history.activities[0] is new


def test_cross_source_duplicate_is_deduped():
    """Garmin sincroniza tudo pro Strava: o mesmo treino pode chegar pelas
    duas fontes (ids diferentes, ~3h de offset de fuso) numa transição.
    O dedup colapsa e mantém a corrida recém-concluída (dados completos)."""

    from datetime import datetime, timezone

    # treino novo vindo do Garmin (UTC 10:00 = 07:00 BRT)
    new = make_activity(
        id=999, distance=5020.0, moving_time=2220,
        start_date=datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone.utc),
    )

    # o MESMO treino já arquivado pelo Strava (hora local, id diferente)
    strava_twin = make_activity(
        id=111, distance=5020.0, moving_time=2225,
        start_date=datetime(2026, 7, 12, 7, 0, 0),
    )
    # um treino real DISTINTO no mesmo dia (distância bem diferente): fica
    other_run = make_activity(
        id=222, distance=9000.0, moving_time=3000,
        start_date=datetime(2026, 7, 12, 18, 0, 0),
    )

    with patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive:

        mock_archive.return_value.load_activities.return_value = [
            strava_twin,
            other_run,
        ]

        history = asyncio.run(
            LoadTrainingHistory.execute(activity=new),
        )

    ids = [a.id for a in history.activities]
    assert 111 not in ids          # gêmeo do Strava colapsado
    assert ids == [999, 222]       # fica a nova + o treino distinto do dia


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
