import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.strava.strava_activity_renamer import (
    StravaActivityRenamer,
)

MOD = "app.application.strava.strava_activity_renamer"


def _activity(dist=6000.0, when="2026-09-01T05:30:00", act_id=1, name="x"):

    return SimpleNamespace(
        id=act_id,
        name=name,
        distance=dist,
        start_date=datetime.fromisoformat(when),
    )


def _session(workout_type="Tempo", km=6.0, minutes=None):

    return SimpleNamespace(
        workout_type=workout_type,
        planned_distance_km=km,
        planned_duration_minutes=minutes,
    )


def _run(profile, done, session, strava_recent, active=True, update=True):

    client = MagicMock()
    client.get_last_activities = AsyncMock(return_value=strava_recent)
    client.update_activity = AsyncMock(return_value=update)

    settings = SimpleNamespace(
        strava_rename_active_for=lambda p: active,
    )

    with (
        patch(f"{MOD}.StravaClient", return_value=client),
        patch(f"{MOD}.get_settings", return_value=settings),
    ):

        result = asyncio.run(
            StravaActivityRenamer.rename_to_plan(profile, done, session)
        )

    return result, client


# ---- casos ----------------------------------------------------------------


def test_renames_generic_strava_run_to_plan_name():
    """O caso do Renato: 'Corrida matinal' vira 'Tempo · 6 km'."""

    done = _activity(dist=6010.0)
    strava = [_activity(dist=6000.0, act_id=555, name="Corrida matinal")]

    ok, client = _run("renato2", done, _session("Tempo", km=6.0), strava)

    assert ok is True
    client.update_activity.assert_awaited_once_with(555, "Ritmind · Tempo 6.0km")


def test_skips_when_canary_off():

    ok, client = _run(
        "outro", _activity(), _session(),
        [_activity(name="Corrida matinal")], active=False,
    )

    assert ok is False
    client.get_last_activities.assert_not_awaited()


def test_skips_without_planned_session():

    ok, client = _run("renato2", _activity(), None, [])

    assert ok is False


def test_respects_athlete_custom_name():
    """Nome que o atleta pôs à mão NÃO é sobrescrito."""

    strava = [_activity(dist=6000.0, name="PR no parque 🔥")]

    ok, client = _run("renato2", _activity(dist=6000.0), _session(), strava)

    assert ok is False
    client.update_activity.assert_not_awaited()


def test_skips_when_no_match_on_strava():
    """Distância muito diferente -> não casa -> não renomeia."""

    strava = [_activity(dist=12000.0, name="Corrida matinal")]

    ok, _ = _run("renato2", _activity(dist=6000.0), _session(), strava)

    assert ok is False


def test_idempotent_when_already_named():

    strava = [_activity(dist=6000.0, name="Ritmind · Tempo 6.0km")]

    ok, client = _run("renato2", _activity(dist=6000.0), _session("Tempo", 6.0),
                      strava)

    assert ok is False
    client.update_activity.assert_not_awaited()


# ---- montagem do nome -----------------------------------------------------


def test_plan_name_matches_watch_title_with_distance():
    """O nome é IDÊNTICO ao que foi pro relógio (inclui 'Ritmind ·')."""

    assert StravaActivityRenamer._plan_name(
        _session("Longão Aeróbico", km=13.0)
    ) == "Ritmind · Longão Aeróbico 13.0km"


def test_plan_name_duration_only_has_no_size():
    """Treino por tempo: o relógio não põe minutos no título -> nem o Strava."""

    assert StravaActivityRenamer._plan_name(
        _session("Rodagem por Tempo", km=None, minutes=45)
    ) == "Ritmind · Rodagem por Tempo"


def test_plan_name_empty_without_type():

    assert StravaActivityRenamer._plan_name(_session("", km=6.0)) == ""


# ---- detecção de nome genérico --------------------------------------------


def test_is_generic_recognizes_strava_defaults():

    assert StravaActivityRenamer._is_generic("Corrida matinal")
    assert StravaActivityRenamer._is_generic("Corrida da tarde")
    assert StravaActivityRenamer._is_generic("Morning Run")
    assert StravaActivityRenamer._is_generic("Evening Run")
    assert StravaActivityRenamer._is_generic("")


def test_is_generic_rejects_custom_names():

    assert not StravaActivityRenamer._is_generic("Tempo · 6 km")
    assert not StravaActivityRenamer._is_generic("Treino com a galera")
    assert not StravaActivityRenamer._is_generic("PR 10k")
