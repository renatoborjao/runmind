import json
from unittest.mock import MagicMock, patch

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MODULE = "app.application.coach.memory.runner_memory_service"


def _patched_repos(tmp_path):

    memory_repo = RunnerMemoryRepository()
    memory_repo.storage = tmp_path / "memory"
    memory_repo.storage.mkdir()

    profile_repo = RunnerProfileRepository()
    profile_repo.storage = tmp_path

    profile_file = tmp_path / "renato.json"
    profile_file.write_text(
        json.dumps({
            "id": "1",
            "name": "Renato",
            "injuries": [],
            "notifications": True,
        }),
        encoding="utf-8",
    )

    return memory_repo, profile_repo


def test_process_adds_archives_and_syncs_injuries(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {
                "add": [
                    {"category": "lesao", "content": "Dor no joelho direito"},
                    {"category": "vida", "content": "Semana puxada no trabalho"},
                ],
                "archive": [],
            },
        )

        entries = memory_repo.active("renato")
        assert len(entries) == 2
        assert all(entry.id.startswith("m-") for entry in entries)

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )
        assert profile["injuries"] == ["Dor no joelho direito"]
        # chaves desconhecidas da entidade são preservadas
        assert profile["notifications"] is True

        # segunda rodada: lesão resolvida -> arquiva e limpa injuries
        injury_id = next(
            entry.id
            for entry in entries
            if entry.category == "lesao"
        )

        RunnerMemoryService.process(
            "renato",
            {"add": [], "archive": [injury_id]},
        )

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )
        assert profile["injuries"] == []

        assert len(memory_repo.active("renato")) == 1


def test_render_formats_active_memories(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {
                "add": [
                    {"category": "lesao", "content": "Dor no joelho direito"},
                ],
                "archive": [],
            },
        )

        rendered = RunnerMemoryService.render("renato")

        assert rendered.startswith("Memória do corredor")
        assert "[lesao] Dor no joelho direito (" in rendered


def test_render_returns_empty_string_without_memories(tmp_path):

    memory_repo, _ = _patched_repos(tmp_path)

    with patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo):

        assert RunnerMemoryService.render("renato") == ""


def test_render_limits_to_15_most_recent(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {
                "add": [
                    {"category": "vida", "content": f"Fato {i}"}
                    for i in range(20)
                ],
                "archive": [],
            },
        )

        rendered = RunnerMemoryService.render("renato")

        lines = rendered.splitlines()
        # 1 linha de cabeçalho + 15 memórias
        assert len(lines) == 16
        assert "Fato 19" in lines[-1]
        assert "Fato 4" not in rendered
