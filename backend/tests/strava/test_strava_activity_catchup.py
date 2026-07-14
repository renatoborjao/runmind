import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.strava.strava_activity_catchup import (
    StravaActivityCatchup,
)
from tests.coach.factories import make_activity

MODULE = "app.application.strava.strava_activity_catchup"


def _run_one(
    *,
    token=True,
    garmin_analyzed=False,
    seeded=True,
    activity_ids=(1, 2),
    guard_new=None,
):

    marker = MagicMock()
    marker.exists.return_value = seeded

    guard = MagicMock()
    if guard_new is None:
        guard.check_and_mark.return_value = True
    else:
        guard.check_and_mark.side_effect = lambda aid: guard_new.get(aid, True)

    with (
        patch(f"{MODULE}.TokenStore") as token_store,
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.StravaClient") as strava_cls,
        patch(f"{MODULE}.ProcessedActivityGuard", return_value=guard),
        patch(f"{MODULE}._seeded_marker", return_value=marker),
        patch(f"{MODULE}._SEED_DIR"),
        patch(
            f"{MODULE}.StravaActivityCatchup._analyze", new_callable=AsyncMock
        ) as analyze,
    ):

        token_store.return_value.load.return_value = {"t": 1} if token else None
        garmin.is_connected.return_value = garmin_analyzed
        garmin.analysis_enabled.return_value = garmin_analyzed

        strava = strava_cls.return_value
        strava.get_last_activities = AsyncMock(
            return_value=[make_activity(id=i) for i in activity_ids],
        )

        asyncio.run(StravaActivityCatchup.run_one("renato"))

        return {"analyze": analyze, "guard": guard, "marker": marker}


def test_skips_when_no_strava_token():

    m = _run_one(token=False)

    m["analyze"].assert_not_awaited()


def test_skips_garmin_analyzed_athlete():
    """Analisado via Garmin: coberto pelo poller — não analisa 2x."""

    m = _run_one(garmin_analyzed=True)

    m["analyze"].assert_not_awaited()


def test_seeds_on_first_pass_without_analyzing():
    """Primeira passada: marca as recentes e NÃO analisa (não despeja
    histórico ao ligar o recurso / atleta recém-conectado)."""

    m = _run_one(seeded=False, activity_ids=(10, 11, 12))

    assert m["guard"].check_and_mark.call_count == 3
    m["marker"].write_text.assert_called_once()
    m["analyze"].assert_not_awaited()


def test_analyzes_only_new_activities():
    """Semeado: analisa só o que ainda não passou (dedup), do mais antigo
    pro mais novo."""

    m = _run_one(
        activity_ids=(1, 2, 3),
        guard_new={1: False, 2: True, 3: True},  # 1 já visto
    )

    awaited = [c.args for c in m["analyze"].await_args_list]
    assert ("renato", 3) in awaited
    assert ("renato", 2) in awaited
    assert ("renato", 1) not in awaited


def _analyze(sport="Run", distance=8000.0):

    with (
        patch(f"{MODULE}.StravaClient") as strava_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as event,
        patch(f"{MODULE}.ProcessedActivityGuard"),
    ):

        strava = strava_cls.return_value
        strava.get_activity = AsyncMock(
            return_value=make_activity(sport=sport, distance=distance),
        )
        strava.get_activity_streams = AsyncMock(return_value={})
        event.execute = AsyncMock()

        asyncio.run(StravaActivityCatchup._analyze("renato", 99))

        return event


def test_analyze_processes_foot_run_with_distance():

    event = _analyze(sport="Run", distance=8000.0)

    event.execute.assert_awaited_once()


def test_analyze_skips_non_foot_sport():

    event = _analyze(sport="Ride")

    event.execute.assert_not_awaited()


def test_analyze_skips_activity_without_distance():

    event = _analyze(sport="Run", distance=0.0)

    event.execute.assert_not_awaited()
