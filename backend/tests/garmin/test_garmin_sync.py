import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.garmin.garmin_sync import GarminSync

MODULE = "app.application.garmin.garmin_sync"


def _runner():

    # o fluxo só usa runner.name
    return SimpleNamespace(name="Renato")


def _handle(text, *, pending, connected, push_results=None):

    with (
        patch(f"{MODULE}.GarminOfferStore") as store,
        patch(f"{MODULE}.GarminClient") as client,
        patch(
            f"{MODULE}.push_current_plan", new_callable=AsyncMock
        ) as push,
    ):

        store.is_pending.return_value = pending
        client.is_connected.return_value = connected
        push.return_value = (None, None, push_results or [])

        reply = asyncio.run(
            GarminSync.handle_reply("renato2", _runner(), text)
        )

        return reply, store, push


_OK_LONGAO = [
    {"ok": True, "day": "Saturday", "date": "2026-07-18", "workout": "Longão"},
]


def test_sim_with_pending_offer_pushes():

    reply, store, push = _handle(
        "sim", pending=True, connected=True, push_results=_OK_LONGAO
    )

    push.assert_awaited_once()
    store.clear.assert_called_once()
    assert "Garmin" in reply
    assert "Longão" in reply


def test_sim_without_pending_does_nothing():
    """Sem oferta ativa, um 'sim' solto não sincroniza (evita falso positivo)."""

    reply, _, push = _handle("sim", pending=False, connected=True)

    assert reply is None
    push.assert_not_awaited()


def test_explicit_request_pushes_even_without_offer():

    reply, _, push = _handle(
        "manda pro meu garmin", pending=False, connected=True,
        push_results=_OK_LONGAO,
    )

    push.assert_awaited_once()
    assert "Garmin" in reply


def test_decline_clears_offer_without_pushing():

    reply, store, push = _handle("agora nao", pending=True, connected=True)

    push.assert_not_awaited()
    store.clear.assert_called_once()
    assert "mudar de ideia" in reply.lower()


def test_ambiguous_reply_with_pending_defers_to_gemini():
    """Oferta pendente + resposta que não é claramente sim/não -> None
    (deixa a conversa normal seguir)."""

    reply, _, push = _handle(
        "como foi meu treino de ontem?", pending=True, connected=True
    )

    assert reply is None
    push.assert_not_awaited()


def test_push_with_no_successful_sessions_reports_problem():

    reply, _, push = _handle(
        "sim", pending=True, connected=True,
        push_results=[{"ok": False, "error": "boom", "day": "Sat",
                       "date": "x", "workout": "Longão"}],
    )

    push.assert_awaited_once()
    assert "nao consegui" in reply.lower() or "não consegui" in reply.lower()
