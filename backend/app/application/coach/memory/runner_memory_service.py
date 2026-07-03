from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.memory_entry import MemoryEntry
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MAX_MEMORIES_IN_CONTEXT = 15


class RunnerMemoryService:

    @staticmethod
    def process(
        profile: str,
        ops: dict,
    ) -> None:
        """Aplica as operações extraídas da conversa e sincroniza
        as lesões ativas com o perfil do corredor."""

        repo = RunnerMemoryRepository()

        for item in ops.get("add", []):

            repo.add(
                profile,
                MemoryEntry(
                    id=f"m-{uuid4().hex[:8]}",
                    category=item["category"],
                    content=item["content"],
                    source="conversation",
                    created_at=datetime.now(UTC).isoformat(),
                ),
            )

        repo.archive(
            profile,
            ops.get("archive", []),
        )

        RunnerMemoryService._sync_injuries(
            profile,
            repo,
        )

    @staticmethod
    def render(
        profile: str,
    ) -> str:
        """Memórias ativas formatadas para o contexto da conversa;
        string vazia quando não há nada a lembrar."""

        memories = RunnerMemoryRepository().active(profile)

        if not memories:

            return ""

        recent = memories[-MAX_MEMORIES_IN_CONTEXT:]

        lines = [
            "Memória do corredor (fatos anotados de conversas anteriores):"
        ]

        for entry in recent:

            registered = datetime.fromisoformat(
                entry.created_at
            ).strftime("%d/%m")

            lines.append(
                f"- [{entry.category}] {entry.content} ({registered})"
            )

        return "\n".join(lines)

    @staticmethod
    def _sync_injuries(
        profile: str,
        repo: RunnerMemoryRepository,
    ) -> None:

        injuries = [
            entry.content
            for entry in repo.active(profile)
            if entry.category == "lesao"
        ]

        RunnerProfileRepository().update_injuries(
            profile,
            injuries,
        )
