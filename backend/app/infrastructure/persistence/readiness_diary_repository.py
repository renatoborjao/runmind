"""Diário de prontidão — storage/readiness_diary/{profile}.json.

Um registro por dia (um novo no mesmo dia substitui o anterior — a última
leitura vale), série ordenada, com teto. Gitignored (dado de atleta, como
checkins/). É o 'diário do que o coach diria' em modo observação — a base do
dedup por MUDANÇA DE ESTADO (só falaria quando o veredito vira)."""

import json
from dataclasses import asdict
from pathlib import Path

from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry

# histórico curto basta — o valor está no estado recente e na virada
_MAX = 60


class ReadinessDiaryRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "readiness_diary"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def load(self, profile: str) -> list[ReadinessDiaryEntry]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                return [ReadinessDiaryEntry(**r) for r in json.load(f)]

        except (json.JSONDecodeError, OSError, TypeError):

            return []

    def last(self, profile: str) -> ReadinessDiaryEntry | None:
        """O registro mais recente — o estado ANTERIOR, base do dedup."""

        entries = self.load(profile)

        return entries[-1] if entries else None

    def record(self, profile: str, entry: ReadinessDiaryEntry) -> None:
        """Grava. No MESMO dia, SUBSTITUI (reavaliação pós-treino atualiza o
        veredito do dia em vez de duplicar)."""

        entries = self.load(profile)

        if entries and entries[-1].day == entry.day:

            entries[-1] = entry

        else:

            entries.append(entry)

        self._save(profile, entries[-_MAX:])

    def _save(self, profile: str, entries: list[ReadinessDiaryEntry]) -> None:

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(
                [asdict(e) for e in entries], f, ensure_ascii=False, indent=2
            )
