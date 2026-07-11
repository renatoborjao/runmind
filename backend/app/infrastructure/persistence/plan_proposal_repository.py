import json
from dataclasses import asdict
from pathlib import Path

from app.domain.entities.plan_proposal import PlanProposal


class PlanProposalRepository:
    """Guarda a proposta de mudança PENDENTE de cada atleta (no máximo uma).
    O aceite/recusa a consome; uma proposta nova substitui a anterior."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "proposals"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> PlanProposal | None:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return None

        with open(
            file,
            encoding="utf-8",
        ) as f:

            return PlanProposal(**json.load(f))

    def save(
        self,
        profile: str,
        proposal: PlanProposal,
    ) -> None:

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                asdict(proposal),
                f,
                ensure_ascii=False,
                indent=2,
            )

    def clear(
        self,
        profile: str,
    ) -> None:
        """Some com a proposta pendente (aceita, recusada ou caducada)."""

        file = self.storage / f"{profile}.json"

        if file.exists():

            file.unlink()
