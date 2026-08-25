import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.entities.memory_entry import MemoryEntry
from app.domain.memory_lifecycle import MemoryLifecycle


class RunnerMemoryRepository:

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "memory"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> list[MemoryEntry]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return [
            MemoryEntry(**entry)
            for entry in data
        ]

    def active(
        self,
        profile: str,
    ) -> list[MemoryEntry]:
        """Fatos VIVOS: não arquivados E não vencidos. A validade sai do
        expires_at gravado ou, pra dado legado sem ele, é DERIVADA na hora
        (categoria/conteúdo/data) — assim a higiene vale retroativa, sem
        migração. Ver [[MemoryLifecycle]]."""

        today = date.today()

        return [
            entry
            for entry in self.load(profile)
            if entry.status == "active"
            and not MemoryLifecycle.is_expired(entry, today)
        ]

    def add(
        self,
        profile: str,
        entry: MemoryEntry,
    ) -> None:

        entries = self.load(profile)

        entries.append(entry)

        self._save(profile, entries)

    def archive(
        self,
        profile: str,
        ids: list[str],
    ) -> None:

        if not ids:

            return

        entries = self.load(profile)

        for entry in entries:

            if entry.id in ids:

                entry.status = "archived"

        self._save(profile, entries)

    def _save(
        self,
        profile: str,
        entries: list[MemoryEntry],
    ) -> None:

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                [asdict(entry) for entry in entries],
                f,
                ensure_ascii=False,
                indent=2,
            )
