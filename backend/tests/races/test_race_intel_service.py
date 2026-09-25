"""Dossiê da prova: pesquisa na web UMA vez por prova (cache compartilhado),
ignora prova genérica, previsão só na última semana (1x/dia), e o coach só LÊ."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.races import race_intel_service as ris
from app.application.races.race_intel_service import (
    RaceIntelService,
    _clean,
    is_specific,
    race_key,
)
from app.infrastructure.persistence.race_intel_repository import (
    RaceIntelRepository,
)

TODAY = date(2026, 9, 25)

NAME = "Santander Track&Field Run Series - Villa-Lobos (15 km)"

DOSSIER = {
    "identified": True, "official_name": "Santander T&F Villa-Lobos",
    "city": "São Paulo/SP", "date_confirmed": True, "start_time": "05:15",
    "course": "Av. Prof. Fonseca Rodrigues", "elevation": "plano",
    "elevation_gain_m": None, "hills": [], "surface": "asfalto",
    "hydration": None, "typical_weather": "quente e úmido",
    "strategy_tips": ["ritmo constante desde o início"], "sources": [],
}


@pytest.fixture
def repo(tmp_path, monkeypatch):

    r = RaceIntelRepository()
    r.storage = tmp_path

    monkeypatch.setattr(ris, "RaceIntelRepository", lambda: r)

    return r


def _run(coro):

    return asyncio.run(coro)


@pytest.mark.parametrize("name,expected", [
    ("10 km", False),
    ("15 km", False),
    ("Meia maratona", False),
    ("21k", False),
    ("Maratona do Rio", True),
    (NAME, True),
    ("Nike SP City Marathon 2027 (21 km)", True),
])
def test_is_specific(name, expected):

    assert is_specific(name) is expected


def test_race_key_is_shared_and_safe():

    assert race_key(NAME, "2026-12-20") == race_key(NAME.upper(), "2026-12-20")
    assert "/" not in race_key("../../etc", "2026-12-20")


def test_clean_caps_lists_and_rejects_absurd_numbers():

    out = _clean({"hills": ["a", "b", "c", "d", "e"], "strategy_tips": ["1", "2", "3", "4"],
                  "elevation_gain_m": 99999, "official_name": "  X  "})

    assert len(out["hills"]) == 4
    assert len(out["strategy_tips"]) == 3
    assert out["elevation_gain_m"] is None
    assert out["official_name"] == "X"


def test_generic_or_far_or_past_race_is_never_researched(repo):

    with patch.object(RaceIntelService, "research", new=AsyncMock()) as research:

        assert _run(RaceIntelService.ensure("10 km", "2026-10-10", TODAY)) is None
        assert _run(RaceIntelService.ensure(NAME, "2028-01-01", TODAY)) is None
        assert _run(RaceIntelService.ensure(NAME, "2026-09-01", TODAY)) is None

    research.assert_not_awaited()


def test_research_once_then_cache_hit(repo):

    with patch.object(RaceIntelService, "research", new=AsyncMock(return_value=dict(DOSSIER))) as research:

        first = _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))
        second = _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))

    assert research.await_count == 1
    assert first["official_name"] == second["official_name"]
    assert RaceIntelService.cached(NAME, date(2026, 12, 20))["city"] == "São Paulo/SP"


def test_old_dossier_is_researched_again(repo):

    old = {**DOSSIER, "researched_at": "2026-01-01T10:00:00-03:00"}

    repo.save(race_key(NAME, "2026-12-20"), old)

    with patch.object(RaceIntelService, "research", new=AsyncMock(return_value=dict(DOSSIER))) as research:

        _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))

    research.assert_awaited_once()


def test_forecast_only_in_last_week_and_once_a_day(repo):

    key = race_key(NAME, "2026-09-30")

    repo.save(key, {**DOSSIER, "researched_at": "2026-09-20T10:00:00-03:00"})

    grounded = AsyncMock(return_value=({"forecast": "22°C na largada, sem chuva"}, []))

    with patch.object(ris, "_grounded", new=grounded):

        _run(RaceIntelService.ensure(NAME, "2026-09-30", TODAY))   # D-5: busca
        _run(RaceIntelService.ensure(NAME, "2026-09-30", TODAY))   # mesmo dia: não

    assert grounded.await_count == 1
    assert repo.load(key)["forecast"]["text"].startswith("22°C")

    # longe da prova: sem previsão
    far = race_key(NAME, "2026-12-20")
    repo.save(far, {**DOSSIER, "researched_at": "2026-09-20T10:00:00-03:00"})

    with patch.object(ris, "_grounded", new=AsyncMock()) as g:

        _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))

    g.assert_not_awaited()


def test_unidentified_race_is_cached_but_never_shown(repo):

    with patch.object(RaceIntelService, "research", new=AsyncMock(return_value={"identified": False})) as research:

        _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))
        _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY))

    assert research.await_count == 1  # não pesquisa de novo todo dia
    assert RaceIntelService.cached(NAME, "2026-12-20") is None


def test_research_failure_never_raises(repo):

    with patch.object(RaceIntelService, "research", new=AsyncMock(side_effect=RuntimeError("429"))):

        assert _run(RaceIntelService.ensure(NAME, "2026-12-20", TODAY)) is None


def test_render_context_and_briefing():

    intel = {**DOSSIER, "hills": ["km 9: subida da ponte"], "forecast": {"text": "24°C"}}

    ctx = RaceIntelService.render_context(intel)

    assert "Dossiê da prova" in ctx and "05:15" in ctx and "subida da ponte" in ctx and "24°C" in ctx

    brief = RaceIntelService.briefing(intel)

    assert "📍" in brief and "km 9" in brief and "🌡️ Previsão: 24°C" in brief and "💡" in brief

    assert "💡" not in RaceIntelService.briefing(intel, with_tips=False)
    assert RaceIntelService.render_context(None) == ""
    assert RaceIntelService.briefing(None) == ""


def test_for_runner_reads_anchor_from_cache(repo):

    repo.save(race_key(NAME, "2026-12-20"), dict(DOSSIER))

    runner = SimpleNamespace(target_race=NAME, race_date="2026-12-20")

    assert RaceIntelService.for_runner(runner)["start_time"] == "05:15"
    assert RaceIntelService.for_runner(SimpleNamespace(target_race=None, race_date=None)) is None


def test_refresh_all_researches_each_race_once_across_athletes(repo):

    profiles = SimpleNamespace(
        list_active=lambda: ["a", "b"],
        load=lambda p: SimpleNamespace(target_race=NAME, race_date="2026-12-20"),
    )

    races = SimpleNamespace(load=lambda p: [{"name": NAME, "date": "2026-12-20"}])

    with (
        patch("app.infrastructure.persistence.runner_profile_repository.RunnerProfileRepository", return_value=profiles),
        patch("app.infrastructure.persistence.race_repository.RaceRepository", return_value=races),
        patch.object(RaceIntelService, "ensure", new=AsyncMock()) as ensure,
    ):

        _run(RaceIntelService.refresh_all(TODAY))

    ensure.assert_awaited_once_with(NAME, "2026-12-20", TODAY)
