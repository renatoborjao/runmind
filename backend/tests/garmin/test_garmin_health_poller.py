import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.garmin import garmin_health_poller as module
from app.application.garmin.garmin_health_poller import GarminHealthPoller
from app.domain.entities.daily_health import DailyHealth

MODULE = "app.application.garmin.garmin_health_poller"


def _runner(tz="America/Sao_Paulo"):

    return SimpleNamespace(timezone=tz)


def _patches(has_date, fetched=None):
    """Contexto com now_in fixo (ontem = 2026-07-20), profile carregado e a
    fonte/repo mockados."""

    repo = MagicMock()

    repo.has_date.return_value = has_date

    fetch = MagicMock(return_value=fetched or DailyHealth(date="2026-07-20"))

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    return repo, fetch, profile_repo


def test_pulls_and_stores_yesterday_when_missing():

    repo, fetch, profile_repo = _patches(has_date=False)

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminHealthSource.fetch", fetch),
    ):

        GarminHealthPoller.poll_one("renato2", repo)

    # puxou ONTEM (2026-07-20) e gravou
    fetch.assert_called_once_with("renato2", "2026-07-20")

    repo.upsert.assert_called_once()


def test_skips_garmin_when_date_already_stored():

    repo, fetch, profile_repo = _patches(has_date=True)

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminHealthSource.fetch", fetch),
    ):

        GarminHealthPoller.poll_one("renato2", repo)

    # já tinha o dia: nem bateu no Garmin
    fetch.assert_not_called()

    repo.upsert.assert_not_called()


def test_poll_all_gates_on_connected_and_analysis_enabled():

    seen = []

    def fake_poll_one(profile, repo):

        seen.append(profile)

    profile_repo = MagicMock()

    profile_repo.list_all.return_value = ["conectado", "sem_garmin", "sem_valvula"]

    def connected(p):

        return p in ("conectado", "sem_valvula")

    def analysis(p):

        return p == "conectado"

    with (
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", side_effect=connected),
        patch(f"{MODULE}.GarminClient.analysis_enabled", side_effect=analysis),
        patch.object(GarminHealthPoller, "poll_one", staticmethod(fake_poll_one)),
    ):

        asyncio.run(GarminHealthPoller.poll_all())

    # só o atleta conectado E com a válvula ligada é ingerido
    assert seen == ["conectado"]


def test_poll_all_isolates_failure_per_athlete():

    def fake_poll_one(profile, repo):

        if profile == "quebra":

            raise RuntimeError("garmin fora")

    profile_repo = MagicMock()

    profile_repo.list_all.return_value = ["quebra", "ok"]

    done = []

    def tracking(profile, repo):

        fake_poll_one(profile, repo)

        done.append(profile)

    with (
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch.object(GarminHealthPoller, "poll_one", staticmethod(tracking)),
    ):

        asyncio.run(GarminHealthPoller.poll_all())

    # a falha de um atleta não impede o próximo
    assert done == ["ok"]
