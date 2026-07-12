import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.memory.memory_extraction_engine import (
    MemoryExtractionEngine,
)
from app.domain.entities.memory_entry import MemoryEntry

MODULE = "app.application.coach.memory.memory_extraction_engine"
GEN_TEXT = "app.infrastructure.integrations.gemini.client.generate_text"


def _memory(entry_id: str = "m-1") -> MemoryEntry:

    return MemoryEntry(
        id=entry_id,
        category="lesao",
        content="Dor no joelho direito",
        source="conversation",
        created_at="2026-07-01T10:00:00+00:00",
    )


def _extract(response_text: str | None, **overrides):

    mock_generate = AsyncMock(return_value=response_text or "")

    with patch(GEN_TEXT, new=mock_generate):

        kwargs = dict(
            runner_name="Renato",
            current_memories=[_memory()],
            recent_turns=[{"role": "user", "text": "oi coach"}],
            incoming_text="Senti dor no tornozelo hoje",
        )

        kwargs.update(overrides)

        ops = asyncio.run(
            MemoryExtractionEngine.extract(**kwargs)
        )

        _, call_kwargs = mock_generate.call_args

        return ops, call_kwargs


def test_extract_parses_add_and_archive_ops():

    ops, kwargs = _extract(
        '{"add": [{"category": "lesao", "content": "Dor no tornozelo"}],'
        ' "archive": ["m-1"]}'
    )

    assert ops == {
        "add": [{"category": "lesao", "content": "Dor no tornozelo"}],
        "archive": ["m-1"],
    }

    # o prompt leva memórias atuais, contexto e a mensagem nova
    prompt = kwargs["contents"]
    assert "m-1 — [lesao] Dor no joelho direito" in prompt
    assert "user: oi coach" in prompt
    assert "Senti dor no tornozelo hoje" in prompt

    assert kwargs["config"].response_mime_type == "application/json"


def test_extract_returns_empty_ops_on_malformed_json():

    ops, _ = _extract("resposta que não é json")

    assert ops == {"add": [], "archive": []}


def test_extract_returns_empty_ops_on_none_response():

    ops, _ = _extract(None)

    assert ops == {"add": [], "archive": []}


def test_extract_filters_invalid_categories_and_empty_content():

    ops, _ = _extract(
        '{"add": ['
        '{"category": "invalida", "content": "algo"},'
        '{"category": "lesao", "content": ""},'
        '{"category": "vida", "content": "Semana puxada no trabalho"}'
        '], "archive": [42]}'
    )

    assert ops == {
        "add": [{"category": "vida", "content": "Semana puxada no trabalho"}],
        "archive": [],
    }


def test_extract_parses_race_field():

    ops, kwargs = _extract(
        '{"add": [], "archive": [],'
        ' "race": {"name": "10 km", "date": "2026-08-15",'
        ' "target_time": "00:50:00"}}'
    )

    assert ops["race"] == {
        "name": "10 km",
        "date": "2026-08-15",
        "target_time": "00:50:00",
    }

    # o prompt informa a data de hoje (datas relativas)
    assert "Hoje é" in kwargs["contents"]


def test_extract_parses_race_clear():

    ops, _ = _extract(
        '{"add": [], "archive": [], "race": {"clear": true}}'
    )

    assert ops["race"] == {"clear": True}


def test_race_with_invalid_date_is_dropped():

    ops, _ = _extract(
        '{"add": [], "archive": [],'
        ' "race": {"name": "10 km", "date": "agosto"}}'
    )

    assert "race" not in ops
