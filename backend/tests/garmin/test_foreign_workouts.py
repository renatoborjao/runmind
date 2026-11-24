"""Treinos de FORA do Ritmind no relógio (Renato 24/11: 3 de outra origem + os 3
nossos = "6 treinos"; reenviar não resolvia e o coach prometia "sobrescrever").
O envio aponta quais são e só apaga com o OK do atleta."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.garmin.garmin_push import find_foreign_scheduled
from app.application.garmin.garmin_sync import GarminSync, _wants_foreign_removed
from app.infrastructure.integrations.garmin.foreign_workout_store import (
    ForeignWorkoutStore,
)

MODULE = "app.application.garmin.garmin_sync"

_FOREIGN = [{"workout_id": 11, "title": "Fartlek Curto", "date": "2026-11-26"}]


def _runner():

    return SimpleNamespace(name="Renato", external_coach=False)


def _calendar(items):

    garmin = MagicMock()
    garmin.connectapi.return_value = {"calendarItems": items}

    return garmin


def test_finds_only_scheduled_workouts_that_are_not_ours_in_the_range():

    garmin = _calendar([
        {"itemType": "workout", "title": "Ritmind · Limiar 8.5km", "workoutId": 1, "date": "2026-11-26"},
        {"itemType": "workout", "title": "Fartlek Curto", "workoutId": 11, "date": "2026-11-26"},
        {"itemType": "workout", "title": "Longo Contínuo", "workoutId": 12, "date": "2026-11-28"},
        {"itemType": "workout", "title": "Velho", "workoutId": 13, "date": "2026-11-20"},
        {"itemType": "activity", "title": "Corrida", "workoutId": None, "date": "2026-11-25"},
    ])

    found = find_foreign_scheduled(garmin, date(2026, 11, 24), date(2026, 11, 29))

    assert [f["title"] for f in found] == ["Fartlek Curto", "Longo Contínuo"]
    # mês da API é base zero (novembro = 10)
    garmin.connectapi.assert_called_once_with("/calendar-service/year/2026/month/10")


def test_week_across_two_months_reads_both_and_failure_is_empty():

    garmin = _calendar([])

    find_foreign_scheduled(garmin, date(2026, 11, 30), date(2026, 12, 6))

    assert garmin.connectapi.call_count == 2

    garmin.connectapi.side_effect = RuntimeError("caiu")

    assert find_foreign_scheduled(garmin, date(2026, 11, 30), date(2026, 12, 6)) == []


def test_removal_intent():

    assert _wants_foreign_removed("pode apagar", offer_pending=False)
    assert _wants_foreign_removed("apaga os duplicados por favor", offer_pending=False)
    assert _wants_foreign_removed("sim", offer_pending=False)
    # "sim" com oferta de relógio pendente é sobre o relógio, não sobre apagar
    assert not _wants_foreign_removed("sim", offer_pending=True)
    # mexer no plano não é apagar os de fora
    assert not _wants_foreign_removed("tira o treino de quinta da semana", offer_pending=False)
    assert not _wants_foreign_removed("nao apaga", offer_pending=False)


def test_push_reply_points_the_foreign_workouts_and_arms_the_removal():

    async def fake_push(profile, foreign_out=None):

        foreign_out.extend(_FOREIGN)

        return None, None, [{"ok": True, "day": "Thursday", "date": "2026-11-26", "workout": "Limiar"}]

    with (
        patch(f"{MODULE}.GarminClient") as client,
        patch(f"{MODULE}.push_current_plan", new=AsyncMock(side_effect=fake_push)),
    ):

        client.is_connected.return_value = True

        reply = asyncio.run(GarminSync._push("renato2", _runner()))

    assert "Limiar" in reply
    assert "Fartlek Curto (qui 26/11)" in reply
    assert "pode apagar" in reply
    assert "sobrescrev" not in reply
    assert ForeignWorkoutStore.pending("renato2") == _FOREIGN


def test_pode_apagar_deletes_only_what_still_matches():

    ForeignWorkoutStore.set_pending("renato2", _FOREIGN + [
        {"workout_id": 12, "title": "Longo Contínuo", "date": "2026-11-28"},
    ])

    garmin = MagicMock()
    # o 12 já foi apagado pelo atleta: não mexe
    garmin.get_workouts.return_value = [
        {"workoutId": 11, "workoutName": "Fartlek Curto"},
        {"workoutId": 1, "workoutName": "Ritmind · Limiar 8.5km"},
    ]

    with (
        patch(f"{MODULE}.GarminClient") as client,
        patch(f"{MODULE}.GarminOfferStore") as offers,
        patch(f"{MODULE}.push_current_plan", new_callable=AsyncMock) as push,
    ):

        client.connect.return_value = garmin
        offers.is_pending.return_value = False

        reply = asyncio.run(GarminSync.handle_reply("renato2", _runner(), "pode apagar"))

    garmin.delete_workout.assert_called_once_with(11)
    push.assert_not_awaited()
    assert "Fartlek Curto" in reply
    assert ForeignWorkoutStore.pending("renato2") == []


def test_no_keeps_them_and_closes_the_warning():

    ForeignWorkoutStore.set_pending("renato2", _FOREIGN)

    with (
        patch(f"{MODULE}.GarminClient") as client,
        patch(f"{MODULE}.GarminOfferStore") as offers,
    ):

        offers.is_pending.return_value = False

        reply = asyncio.run(GarminSync.handle_reply("renato2", _runner(), "não"))

    client.connect.assert_not_called()
    assert "deixo" in reply
    assert ForeignWorkoutStore.pending("renato2") == []
