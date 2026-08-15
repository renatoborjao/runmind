import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.race_workout_flow import RaceWorkoutFlow
from tests.coach.factories import make_runner

MOD = "app.application.coach.conversation.race_workout_flow"


def _reply(text, *, pending=True, connected=True, push=None, external=False):

    runner = make_runner(name="Renato")
    runner.external_coach = external

    with (
        patch(f"{MOD}.RaceWorkoutOfferStore") as store,
        patch(f"{MOD}.GarminClient") as gc,
        patch(f"{MOD}.push_race_workout", new=AsyncMock(return_value=push)),
    ):

        store.is_pending.return_value = pending
        gc.is_connected.return_value = connected

        result = asyncio.run(
            RaceWorkoutFlow.resolve_watch_reply("renato2", runner, text)
        )

        return result, store


def test_sim_pushes_race_and_confirms():

    reply, store = _reply(
        "sim", push={"ok": True, "workout_id": 1, "date": "2026-08-23"},
    )

    assert reply is not None
    assert "Garmin" in reply and "2026-08-23" in reply
    store.clear.assert_called_once_with("renato2")


def test_nao_encerra_sem_empurrar():

    reply, store = _reply("não")

    assert "mudar de ideia" in reply
    store.clear.assert_called_once_with("renato2")


def test_sem_oferta_pendente_passa_direto():

    reply, _ = _reply("sim", pending=False)

    assert reply is None


def test_resposta_ambigua_deixa_conversa_seguir():

    reply, store = _reply("e o pace do longão?")

    assert reply is None
    store.clear.assert_not_called()


def test_treinador_externo_nao_recebe():

    reply, _ = _reply("sim", external=True)

    assert reply is None


def test_push_falho_avisa_sem_quebrar():

    reply, _ = _reply("sim", push=None)

    assert "não consegui" in reply.lower() or "problema" in reply.lower()
