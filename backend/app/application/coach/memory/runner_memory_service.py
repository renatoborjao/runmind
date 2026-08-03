from datetime import datetime
from uuid import uuid4

from app.core.clock import now_local
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
                    # hora local: a data exibida no contexto ("03/07")
                    # tem que bater com o dia do corredor
                    created_at=now_local().isoformat(),
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

        RunnerMemoryService._sync_race(
            profile,
            ops.get("race"),
        )

    @staticmethod
    def render(
        profile: str,
    ) -> str:
        """Memórias ativas formatadas para o contexto da conversa;
        string vazia quando não há nada a lembrar."""

        # a motivação sai numa seção PRÓPRIA (a âncora emocional) — aqui ficam
        # só os fatos operacionais, pra o "porquê" não virar mais um item de lista
        memories = [
            m
            for m in RunnerMemoryRepository().active(profile)
            if m.category != "motivacao"
        ]

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
    def motivation_anchor(profile: str) -> str:
        """A ÂNCORA EMOCIONAL do atleta (por que ele corre) + a diretriz de usá-la
        com verdade nos momentos que importam. Seção distinta da memória de fatos.
        Vazio quando ele ainda não revelou um porquê."""

        anchors = [
            m
            for m in RunnerMemoryRepository().active(profile)
            if m.category == "motivacao"
        ]

        if not anchors:

            return ""

        lines = [
            "POR QUE ELE CORRE (a âncora emocional — o que a corrida significa "
            "pra ele):"
        ]

        for entry in anchors:

            lines.append(f"- {entry.content}")

        lines.append(
            "Puxe isso pra motivar nos momentos que IMPORTAM (semana dura, dia "
            "de baixa, um marco batido) — com as palavras DELE, de forma "
            "genuína. NÃO force em toda mensagem nem repita como bordão: é o que "
            "faz você CONHECER o atleta, não um slogan."
        )

        return "\n".join(lines)

    @staticmethod
    def _sync_race(
        profile: str,
        race: dict | None,
    ) -> None:
        """Prova alvo mencionada na conversa vira dado do perfil —
        o planejamento (fase, goal) passa a olhar pra ela."""

        if race is None:

            return

        if race.get("clear") is True:

            updates = {
                "target_race": None,
                "race_date": None,
                "target_time": None,
            }

        else:

            updates = {"race_date": race["date"]}

            if race.get("name"):

                updates["target_race"] = race["name"]

            if race.get("target_time"):

                updates["target_time"] = race["target_time"]

        RunnerProfileRepository().update_fields(
            profile,
            updates,
        )

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
