from app.domain.entities.plan_proposal import PlanProposal
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)


def _repo(tmp_path) -> PlanProposalRepository:

    repo = PlanProposalRepository()
    repo.storage = tmp_path / "proposals"
    repo.storage.mkdir()

    return repo


def _proposal() -> PlanProposal:

    return PlanProposal(
        kind="aversion",
        week_start="2026-07-06",
        preview="Troco o tiro de terça por um fartlek na rua. Aplico?",
        created_at="2026-07-07T09:00:00",
        operations=[
            {"action": "replace", "day": "Tuesday", "session": {"x": 1}},
        ],
    )


def test_load_returns_none_without_a_proposal(tmp_path):

    assert _repo(tmp_path).load("renato") is None


def test_save_then_load_roundtrips(tmp_path):

    repo = _repo(tmp_path)

    repo.save("renato", _proposal())

    loaded = repo.load("renato")

    assert loaded.kind == "aversion"
    assert loaded.week_start == "2026-07-06"
    assert loaded.operations[0]["day"] == "Tuesday"


def test_clear_removes_the_pending_proposal(tmp_path):

    repo = _repo(tmp_path)

    repo.save("renato", _proposal())

    repo.clear("renato")

    assert repo.load("renato") is None


def test_save_replaces_previous_proposal(tmp_path):

    repo = _repo(tmp_path)

    repo.save("renato", _proposal())

    newer = _proposal()
    newer.preview = "Nova proposta"

    repo.save("renato", newer)

    assert repo.load("renato").preview == "Nova proposta"
