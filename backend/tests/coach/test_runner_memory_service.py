import json
from unittest.mock import patch

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.domain.entities.memory_entry import MemoryEntry
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


def test_illness_marked_as_lesao_does_not_become_injury(tmp_path):
    """Rede de segurança: gripe NÃO é lesão. Mesmo que a extração escorregue e
    marque uma doença passageira como 'lesao', ela não vira 'histórico de lesão'
    no perfil (queixa do Renato pós-prova). A lesão de verdade entra normal."""

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {
                "add": [
                    {"category": "lesao",
                     "content": "Sintomas de gripe com bastante catarro"},
                    {"category": "lesao", "content": "Dor no joelho direito"},
                ],
                "archive": [],
            },
        )

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )

        # a gripe foi filtrada; a lesão real ficou
        assert profile["injuries"] == ["Dor no joelho direito"]


def test_add_supersedes_near_duplicate(tmp_path):
    """Fato novo quase-igual SUPERA o antigo (dedup na entrada) — nada de dois
    'longos aos domingos' na memória."""

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {"add": [{"category": "preferencia",
                      "content": "Prefere treinos longos aos domingos"}],
             "archive": []},
        )
        RunnerMemoryService.process(
            "renato",
            {"add": [{"category": "preferencia",
                      "content": "Prefere treinos longos aos domingos por causa "
                                 "dos exames de sábado"}],
             "archive": []},
        )

        active = memory_repo.active("renato")
        conteudos = [e.content for e in active]

    assert len(active) == 1
    assert "exames" in conteudos[0]  # ficou o mais novo


def test_expired_memory_drops_from_active(tmp_path):
    """Fato com validade vencida não aparece mais (nem no injeta, nem no
    render)."""

    memory_repo, _ = _patched_repos(tmp_path)

    memory_repo.add("renato", MemoryEntry(
        id="m-old", category="disponibilidade",
        content="Trocar treino só nesta semana",
        source="conversation", created_at="2026-01-01T10:00:00-03:00",
        expires_at="2026-01-11",
    ))
    memory_repo.add("renato", MemoryEntry(
        id="m-live", category="preferencia", content="Corre na rua",
        source="conversation", created_at="2026-01-01T10:00:00-03:00",
    ))

    ids = [e.id for e in memory_repo.active("renato")]

    assert ids == ["m-live"]


def test_consolidate_dedups_the_backlog(tmp_path):
    """Backlog com duplicata antiga: consolidate mantém a MAIS NOVA."""

    memory_repo, profile_repo = _patched_repos(tmp_path)

    memory_repo.add("renato", MemoryEntry(
        id="m-1", category="preferencia",
        content="Deseja que os treinos sejam enviados para o relógio Garmin",
        source="conversation", created_at="2026-07-12T10:00:00-03:00",
    ))
    memory_repo.add("renato", MemoryEntry(
        id="m-2", category="preferencia",
        content="Deseja que os treinos sejam enviados para o relógio Garmin "
                "atualizados",
        source="conversation", created_at="2026-08-10T10:00:00-03:00",
    ))

    with patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo):

        RunnerMemoryService.consolidate("renato", memory_repo)

    ids = [e.id for e in memory_repo.active("renato")]

    assert ids == ["m-2"]  # ficou a mais nova


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


def test_race_op_updates_profile(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {
                "add": [],
                "archive": [],
                "race": {
                    "name": "10 km",
                    "date": "2026-08-15",
                    "target_time": "00:50:00",
                },
            },
        )

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )
        assert profile["race_date"] == "2026-08-15"
        assert profile["target_race"] == "10 km"
        assert profile["target_time"] == "00:50:00"
        # chaves desconhecidas preservadas
        assert profile["notifications"] is True


def test_race_clear_wipes_race_fields(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {"add": [], "archive": [],
             "race": {"name": "10 km", "date": "2026-08-15",
                      "target_time": None}},
        )

        RunnerMemoryService.process(
            "renato",
            {"add": [], "archive": [], "race": {"clear": True}},
        )

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )
        assert profile["race_date"] is None
        assert profile["target_race"] is None
        assert profile["target_time"] is None


def test_ops_without_race_do_not_touch_profile_race(tmp_path):

    memory_repo, profile_repo = _patched_repos(tmp_path)

    with (
        patch(f"{MODULE}.RunnerMemoryRepository", return_value=memory_repo),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
    ):

        RunnerMemoryService.process(
            "renato",
            {"add": [{"category": "vida", "content": "Semana puxada"}],
             "archive": []},
        )

        profile = json.loads(
            (tmp_path / "renato.json").read_text(encoding="utf-8")
        )
        assert "race_date" not in profile
