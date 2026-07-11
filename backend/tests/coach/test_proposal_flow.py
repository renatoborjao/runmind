from datetime import timedelta
from unittest.mock import MagicMock, patch

from app.application.coach.conversation.proposal_flow import ProposalFlow
from app.core.clock import now_local
from app.domain.entities.plan_proposal import PlanProposal

MODULE = "app.application.coach.conversation.proposal_flow"


def _proposal(created=None) -> PlanProposal:

    return PlanProposal(
        kind="aversion",
        week_start="2026-07-06",
        preview="Troco o tiro por fartlek. Aplico?",
        created_at=(created or now_local()).isoformat(),
        operations=[{"action": "drop", "day": "Tuesday"}],
    )


def _patched(proposal, applied="PLANO"):

    repo = MagicMock()
    repo.load.return_value = proposal

    applier = MagicMock()
    applier.apply.return_value = applied

    ctx = patch(f"{MODULE}.PlanProposalRepository", return_value=repo)
    ctx2 = patch(f"{MODULE}.PlanChangeApplier", applier)

    return repo, applier, ctx, ctx2


def test_no_pending_proposal_returns_none():

    with patch(f"{MODULE}.PlanProposalRepository") as repo_cls:

        repo_cls.return_value.load.return_value = None

        assert ProposalFlow.resolve("renato", "sim") is None


def test_confirm_applies_and_clears():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = ProposalFlow.resolve("renato", "pode aplicar")

    applier.apply.assert_called_once()
    repo.clear.assert_called_once_with("renato")
    assert "Ajustei" in reply


def test_confirm_on_stale_week_explains_instead_of_applying():

    repo, applier, c1, c2 = _patched(_proposal(), applied=None)

    with c1, c2:

        reply = ProposalFlow.resolve("renato", "sim")

    repo.clear.assert_called_once()
    assert "semana virou" in reply


def test_reject_clears_without_applying():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = ProposalFlow.resolve("renato", "não, deixa quieto")

    applier.apply.assert_not_called()
    repo.clear.assert_called_once()
    assert "deixo como está" in reply


def test_unclear_keeps_proposal_pending():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = ProposalFlow.resolve("renato", "e o longão de sábado?")

    assert reply is None
    applier.apply.assert_not_called()
    repo.clear.assert_not_called()


def test_expired_proposal_is_cleared_and_ignored():

    old = now_local() - timedelta(hours=48)

    repo, applier, c1, c2 = _patched(_proposal(created=old))

    with c1, c2:

        reply = ProposalFlow.resolve("renato", "sim")

    assert reply is None
    repo.clear.assert_called_once()
    applier.apply.assert_not_called()
