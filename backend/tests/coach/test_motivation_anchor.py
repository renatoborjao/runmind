from unittest.mock import patch

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.domain.entities.memory_entry import MEMORY_CATEGORIES, MemoryEntry

REPO = (
    "app.application.coach.memory.runner_memory_service."
    "RunnerMemoryRepository"
)


def _entry(category, content, id="m-1"):

    return MemoryEntry(
        id=id,
        category=category,
        content=content,
        source="conversation",
        created_at="2026-08-03T10:00:00-03:00",
    )


def test_motivacao_is_a_valid_category():

    assert "motivacao" in MEMORY_CATEGORIES


def test_anchor_renders_why_and_directive():

    active = [_entry("motivacao", "Corre pela saúde depois de um susto no coração")]

    with patch(REPO) as repo:
        repo.return_value.active.return_value = active

        out = RunnerMemoryService.motivation_anchor("renato2")

    assert "POR QUE ELE CORRE" in out
    assert "susto no coração" in out
    assert "momentos que IMPORTAM" in out  # a diretriz de uso autêntico


def test_anchor_empty_without_motivacao():

    with patch(REPO) as repo:
        repo.return_value.active.return_value = [_entry("preferencia", "esteira")]

        assert RunnerMemoryService.motivation_anchor("renato2") == ""


def test_render_excludes_motivacao_from_the_fact_list():
    """O porquê não vira mais um item de lista — sai só na âncora."""

    active = [
        _entry("preferencia", "Prefere correr na rua", id="m-1"),
        _entry("motivacao", "Corre pra aliviar o stress do trabalho", id="m-2"),
    ]

    with patch(REPO) as repo:
        repo.return_value.active.return_value = active

        rendered = RunnerMemoryService.render("renato2")

    assert "rua" in rendered
    assert "stress do trabalho" not in rendered
