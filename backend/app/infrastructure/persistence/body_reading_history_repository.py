import json
from dataclasses import asdict
from pathlib import Path

from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot


class BodyReadingHistoryRepository:
    """Guarda o histórico de leituras do corpo em
    storage/body_readings/{profile}.json (antigo -> novo). É o que dá memória
    à leitura: a de hoje sabe de onde o atleta veio.

    Grava no MÁXIMO um snapshot por dia (releituras do mesmo dia colapsam pra
    a série não inflar quando o atleta pergunta várias vezes) e mantém só os
    últimos _MAX (janela de ~6 meses — o suficiente pra trajetória)."""

    _MAX = 26

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "body_readings"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> list[BodyReadingSnapshot]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(file, encoding="utf-8") as f:

            data = json.load(f)

        return [BodyReadingSnapshot(**entry) for entry in data]

    def record(
        self,
        profile: str,
        snapshot: BodyReadingSnapshot,
    ) -> None:
        """Anexa a leitura — mas se a última já é do mesmo dia, SUBSTITUI (uma
        por dia). Corta pelo cap mantendo as mais recentes."""

        snapshots = self.load(profile)

        if snapshots and snapshots[-1].day == snapshot.day:

            snapshots[-1] = snapshot

        else:

            snapshots.append(snapshot)

        self._save(profile, snapshots[-self._MAX:])

    def _save(
        self,
        profile: str,
        snapshots: list[BodyReadingSnapshot],
    ) -> None:

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(
                [asdict(s) for s in snapshots],
                f,
                ensure_ascii=False,
                indent=2,
            )
