import asyncio

import httpx

from app.application.history.best_effort_refresh import BestEffortRefresh
from app.infrastructure.persistence.form_fatigue_store import FormFatigueStore


def _store(tmp_path) -> FormFatigueStore:

    store = FormFatigueStore()

    store.storage = tmp_path

    return store


def _status_error(code: int) -> httpx.HTTPStatusError:

    request = httpx.Request("GET", "https://www.strava.com/api/v3/x")

    return httpx.HTTPStatusError(
        "boom", request=request, response=httpx.Response(code, request=request)
    )


class _Client:

    def __init__(self, error=None, streams=None):

        self.error = error

        self.streams = streams or {}

    async def get_activity_streams(self, activity_id):

        if self.error:

            raise self.error

        return self.streams


def test_mark_processed_does_not_touch_the_fatigue_window(tmp_path):

    store = _store(tmp_path)

    store.record("ana", 1, True)

    store.mark_processed("ana", 2)

    assert store.processed_ids("ana") == {1, 2}

    # a janela segue só com a corrida que tinha série
    assert store._load("ana")["recent"] == [True]


def test_manual_run_without_streams_is_marked_seen_not_retried(tmp_path):
    """Treino lançado à mão: o Strava dá 404 nas séries. Fica como visto (não
    repete a chamada nem o erro todo domingo) e não entra na janela."""

    store = _store(tmp_path)

    done = asyncio.run(
        BestEffortRefresh._do_fade(_Client(_status_error(404)), store, "leo", 7)
    )

    assert done is False

    assert store.processed_ids("leo") == {7}

    assert store._load("leo")["recent"] == []


def test_other_http_errors_stay_retryable(tmp_path):
    """429/5xx são transitórios — NÃO dá por visto, tenta de novo depois."""

    store = _store(tmp_path)

    done = asyncio.run(
        BestEffortRefresh._do_fade(_Client(_status_error(429)), store, "leo", 7)
    )

    assert done is False

    assert store.processed_ids("leo") == set()


def test_run_with_streams_is_recorded(tmp_path):

    store = _store(tmp_path)

    client = _Client(streams={"cadence": [85] * 100, "distance": [7000]})

    done = asyncio.run(BestEffortRefresh._do_fade(client, store, "leo", 9))

    assert done is True

    assert store.processed_ids("leo") == {9}

    assert store._load("leo")["recent"] == [False]
