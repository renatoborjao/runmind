import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.core.clock import now_local
from app.domain.entities.coach_learning import CoachLearning


class CoachLearningRepository:
    """Persiste os aprendizados do coach em storage/learnings/{profile}.json.
    Espelha o RunnerMemoryRepository, com filtro de EXPIRAÇÃO no active() e
    reconfirmação (empurra a validade + sobe a contagem de evidência)."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "learnings"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> list[CoachLearning]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return [
            CoachLearning(**entry)
            for entry in data
        ]

    def active(
        self,
        profile: str,
    ) -> list[CoachLearning]:
        """Aprendizados vivos: status ativo E ainda não expirados. Um
        aprendizado vencido é tratado como esquecido (não some do disco —
        fica pro histórico/debug —, só não conta mais)."""

        now = now_local()

        return [
            entry
            for entry in self.load(profile)
            if entry.status == "active"
            and not self._expired(entry, now)
        ]

    def add(
        self,
        profile: str,
        entry: CoachLearning,
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

    def reconfirm(
        self,
        profile: str,
        ids: list[str],
        expires_at: str,
    ) -> None:
        """Nova evidência sustentou o aprendizado: empurra a validade adiante
        e sobe a contagem de evidência (quanto mais semanas confirmam, mais
        confiável). Ignora ids que não existem/estão arquivados."""

        if not ids:

            return

        entries = self.load(profile)

        for entry in entries:

            if entry.id in ids and entry.status == "active":

                entry.expires_at = expires_at

                entry.evidence_count += 1

        self._save(profile, entries)

    @staticmethod
    def _expired(
        entry: CoachLearning,
        now: datetime,
    ) -> bool:

        try:

            return datetime.fromisoformat(entry.expires_at) < now

        except (ValueError, TypeError):

            # validade ilegível: trata como vivo (não some por dado torto)
            return False

    def _save(
        self,
        profile: str,
        entries: list[CoachLearning],
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
