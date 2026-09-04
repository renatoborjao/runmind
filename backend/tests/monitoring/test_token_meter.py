"""Medidor de tokens do Gemini por atleta: grava por escopo, agrega no report,
e é best-effort (nunca derruba a chamada)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai import types

from app.application.monitoring.token_meter import TokenMeter
from app.infrastructure.integrations.gemini.client import generate_text
from app.infrastructure.persistence.token_usage_repository import (
    TokenUsageRepository,
)

METER = "app.application.monitoring.token_meter"


def _repo(tmp_path) -> TokenUsageRepository:
    repo = TokenUsageRepository()
    repo.storage = tmp_path
    return repo


def _usage(pin, pout, th, total):
    return SimpleNamespace(
        prompt_token_count=pin, candidates_token_count=pout,
        thoughts_token_count=th, total_token_count=total,
    )


def test_record_and_report_aggregates(tmp_path):

    repo = _repo(tmp_path)

    with patch(f"{METER}.TokenUsageRepository", return_value=repo):

        with TokenMeter.scope("renato2", "chat"):
            TokenMeter.record("gemini-3.6-flash", _usage(1000, 200, 50, 1250))

        with TokenMeter.scope("renato2", "plan"):
            TokenMeter.record("gemini-3.1-pro-preview", _usage(5000, 800, 2000, 7800))

        rep = TokenMeter.report("renato2")

    assert rep["calls"] == 2
    assert rep["in"] == 6000
    assert rep["out"] == 1000
    assert rep["thoughts"] == 2050
    assert rep["total"] == 1250 + 7800
    assert rep["by_label"]["chat"]["calls"] == 1
    assert rep["by_label"]["plan"]["total"] == 7800
    assert set(rep["by_model"]) == {"gemini-3.6-flash", "gemini-3.1-pro-preview"}


def test_scope_attributes_to_right_profile_and_resets(tmp_path):

    repo = _repo(tmp_path)

    with patch(f"{METER}.TokenUsageRepository", return_value=repo):

        with TokenMeter.scope("mauricio", "briefing"):
            TokenMeter.record("gemini-3.6-flash", _usage(300, 40, 0, 340))

        # fora do escopo -> default "unknown" (não vaza pro mauricio)
        TokenMeter.record("gemini-3.6-flash", _usage(10, 2, 0, 12))

        assert TokenMeter.report("mauricio")["calls"] == 1
        assert TokenMeter.report("unknown")["calls"] == 1


def test_record_is_best_effort_on_missing_usage(tmp_path):

    repo = _repo(tmp_path)

    with patch(f"{METER}.TokenUsageRepository", return_value=repo):

        with TokenMeter.scope("helio", "chat"):
            TokenMeter.record("m", None)          # sem usage: no-op
            TokenMeter.record("m", object())      # sem os campos: conta 0, não crasha

        rep = TokenMeter.report("helio")

    # a chamada None não grava; a sem-campos grava com zeros (não derruba)
    assert rep["calls"] == 1
    assert rep["total"] == 0


def test_generate_text_records_usage_at_the_choke_point(tmp_path):
    """A instrumentação está no ÚNICO ponto por onde todo Gemini passa:
    generate_text grava o consumo da chamada, atribuído ao escopo."""

    repo = _repo(tmp_path)

    resp = SimpleNamespace(text="ok", usage_metadata=_usage(100, 20, 5, 125))

    fake = MagicMock()
    fake.aio.models.generate_content = AsyncMock(return_value=resp)

    with (
        patch(
            "app.infrastructure.integrations.gemini.client._client",
            return_value=fake,
        ),
        patch(f"{METER}.TokenUsageRepository", return_value=repo),
    ):

        with TokenMeter.scope("fernanda", "analysis"):
            text = asyncio.run(
                generate_text(
                    model="gemini-3.6-flash",
                    contents="oi",
                    config=types.GenerateContentConfig(),
                )
            )

        rep = TokenMeter.report("fernanda")

    assert text == "ok"
    assert rep["calls"] == 1
    assert rep["total"] == 125
    assert rep["by_label"]["analysis"]["calls"] == 1
