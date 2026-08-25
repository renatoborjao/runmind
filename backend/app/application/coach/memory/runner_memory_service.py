from datetime import datetime
from uuid import uuid4

from app.core.clock import now_local
from app.domain.entities.memory_entry import MemoryEntry
from app.domain.memory_lifecycle import MemoryLifecycle
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

MAX_MEMORIES_IN_CONTEXT = 15

# Rede de segurança pro campo DURÁVEL `injuries` (liga "histórico de lesão" e
# sobe o risco de base): mesmo que a extração escorregue e marque uma DOENÇA
# passageira como "lesao", ela NÃO vira lesão do perfil. Doença é estado de
# saúde temporário (cuidado pelo acompanhamento de bem-estar), não lesão
# musculoesquelética. Ver [[project_ideias_produto]] (gripe≠lesão).
_ILLNESS_HINTS = (
    "gripe", "resfriad", "virose", "febre", "catarro", "gargant",
    "tosse", "covid", "sinusite", "rinite", "dengue", "infecç",
    "indispost", "mal-estar", "mal estar", "náusea", "nausea", "enjoo",
    "diarre", "vômito", "vomito",
)


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

            RunnerMemoryService._add(repo, profile, item)

        repo.archive(
            profile,
            ops.get("archive", []),
        )

        # higiene do backlog: junta quase-duplicatas antigas (o active já deixa
        # os vencidos caírem) — auto-cura a memória a cada op, sem esperar limpeza
        RunnerMemoryService.consolidate(profile, repo)

        RunnerMemoryService._sync_injuries(
            profile,
            repo,
        )

        RunnerMemoryService._sync_race(
            profile,
            ops.get("race"),
        )

    @staticmethod
    def _add(repo: RunnerMemoryRepository, profile: str, item: dict) -> None:
        """Grava um fato novo com VALIDADE (durável ou datada/temporária) e,
        antes, SUPERA os ativos quase-iguais da mesma categoria (dedup — a
        frase nova é a mais atual)."""

        category = item["category"]
        content = item["content"]

        # hora local: a data exibida no contexto ("03/07") bate com o dia dele
        created_at = now_local().isoformat()

        superseded = [
            entry.id
            for entry in repo.active(profile)
            if entry.category == category
            and MemoryLifecycle.is_near_duplicate(entry.content, content)
        ]

        if superseded:

            repo.archive(profile, superseded)

        repo.add(
            profile,
            MemoryEntry(
                id=f"m-{uuid4().hex[:8]}",
                category=category,
                content=content,
                source="conversation",
                created_at=created_at,
                expires_at=MemoryLifecycle.expiry_for(
                    category, content, created_at,
                ),
            ),
        )

    @staticmethod
    def consolidate(
        profile: str,
        repo: RunnerMemoryRepository | None = None,
    ) -> None:
        """Higiene do BACKLOG: entre os fatos ativos (o `active` já tirou os
        vencidos), arquiva as quase-duplicatas mantendo a MAIS NOVA. Idempotente
        e conservador (mesma categoria, limiar alto) — falso-merge é pior que
        duplicata. Ver [[MemoryLifecycle]]."""

        repo = repo or RunnerMemoryRepository()

        # ordem cronológica (append) -> o de índice menor é o mais ANTIGO
        active = repo.active(profile)

        stale: list[str] = []

        for index, entry in enumerate(active):

            if entry.id in stale:

                continue

            for newer in active[index + 1:]:

                if (
                    entry.category == newer.category
                    and MemoryLifecycle.is_near_duplicate(
                        entry.content, newer.content,
                    )
                ):

                    # some com o ANTIGO (entry); fica o mais novo (newer)
                    stale.append(entry.id)

                    break

        if stale:

            repo.archive(profile, stale)

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
            and not RunnerMemoryService._is_illness(entry.content)
        ]

        RunnerProfileRepository().update_injuries(
            profile,
            injuries,
        )

    @staticmethod
    def _is_illness(content: str) -> bool:
        """Doença passageira (gripe & cia) — NÃO é lesão do perfil."""

        text = content.lower()

        return any(hint in text for hint in _ILLNESS_HINTS)
