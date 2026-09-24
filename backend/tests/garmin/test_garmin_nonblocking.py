"""A lib do Garmin é SÍNCRONA (rede + pausas de ritmo). Rodada direto no loop,
um poll de ~40s deixava o servidor INTEIRO sem atender (app 'não carrega',
restart levando 43s pra reagir ao SIGTERM — 24/09). Agora vai pra thread: o
loop segue livre. E o login (que pode regravar o token) é serializado por
atleta, pra poller e push do app não se atropelarem."""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

from app.application.garmin.garmin_activity_poller import GarminActivityPoller
from app.application.garmin.garmin_health_poller import GarminHealthPoller
from app.infrastructure.integrations.garmin import garmin_client

HEALTH = "app.application.garmin.garmin_health_poller"
ACTIVITY = "app.application.garmin.garmin_activity_poller"


async def _loop_stays_free(poll) -> int:
    """Roda `poll` e, em paralelo, conta ticks de 20ms do loop. Loop travado
    = ~0 ticks durante o poll."""

    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.02)

    t = asyncio.create_task(ticker())
    await poll()
    done.set()
    await t
    return ticks


def _slow(*a, **k):
    time.sleep(0.5)  # rede/pausa síncrona do Garmin


def test_health_poll_does_not_block_the_server():
    with (
        patch(f"{HEALTH}.RunnerProfileRepository") as repo,
        patch(f"{HEALTH}.GarminClient") as client,
        patch(f"{HEALTH}.GarminHealthRepository"),
        patch.object(GarminHealthPoller, "poll_one", side_effect=_slow),
    ):
        repo.return_value.list_all.return_value = ["renato2"]
        client.is_connected.return_value = True
        client.analysis_enabled.return_value = True

        ticks = asyncio.run(_loop_stays_free(GarminHealthPoller.poll_all))

    assert ticks >= 10  # ~25 ticks em 0.5s; travado daria 1


def test_activity_poll_does_not_block_the_server(tmp_path):
    marker = tmp_path / "seeded"
    marker.touch()

    with (
        patch(f"{ACTIVITY}._seeded_marker", return_value=marker),
        patch.object(
            GarminActivityPoller, "_recent_activities",
            side_effect=lambda p: (_slow(), [])[1],
        ),
    ):
        ticks = asyncio.run(
            _loop_stays_free(lambda: GarminActivityPoller.poll_one("renato2"))
        )

    assert ticks >= 10


def test_login_is_serialized_per_athlete(monkeypatch, tmp_path):
    """Dois logins do MESMO atleta nunca ao mesmo tempo (token em disco);
    atletas diferentes seguem em paralelo."""

    active: dict[str, int] = {}
    peak: dict[str, int] = {}
    lock = threading.Lock()

    class FakeGarmin:
        def login(self, token_dir):
            name = token_dir.split("/")[-1].split("\\")[-1]
            with lock:
                active[name] = active.get(name, 0) + 1
                peak[name] = max(peak.get(name, 0), active[name])
            time.sleep(0.05)
            with lock:
                active[name] -= 1

    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)
    monkeypatch.setattr(
        garmin_client.GarminClient, "is_connected", staticmethod(lambda p: True)
    )
    monkeypatch.setattr(
        garmin_client.GarminClient, "token_dir",
        staticmethod(lambda p: tmp_path / p),
    )

    threads = [
        threading.Thread(target=garmin_client.GarminClient.connect, args=(p,))
        for p in ["renato2"] * 4 + ["fernanda"] * 4
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak["renato2"] == 1
    assert peak["fernanda"] == 1
