import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.proposal_flow import ProposalFlow
from app.core.clock import now_local
from app.domain.entities.plan_proposal import PlanProposal

MODULE = "app.application.coach.conversation.proposal_flow"

_RUNNER = MagicMock()


def _proposal(created=None, kind="aversion", source_text="") -> PlanProposal:

    return PlanProposal(
        kind=kind,
        week_start="2026-07-06",
        preview="Troco o tiro por fartlek. Aplico?",
        created_at=(created or now_local()).isoformat(),
        operations=[{"action": "drop", "day": "Tuesday"}],
        source_text=source_text,
    )


def _patched(proposal, applied="PLANO"):

    repo = MagicMock()
    repo.load.return_value = proposal

    applier = MagicMock()
    applier.apply.return_value = applied

    ctx = patch(f"{MODULE}.PlanProposalRepository", return_value=repo)
    ctx2 = patch(f"{MODULE}.PlanChangeApplier", applier)

    return repo, applier, ctx, ctx2


def _resolve(text):

    return asyncio.run(ProposalFlow.resolve("renato", _RUNNER, text))


def test_no_pending_proposal_returns_none():

    with patch(f"{MODULE}.PlanProposalRepository") as repo_cls:

        repo_cls.return_value.load.return_value = None

        assert _resolve("sim") is None


def test_confirm_applies_and_clears():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = _resolve("pode aplicar")

    applier.apply.assert_called_once()
    repo.clear.assert_called_once_with("renato")
    assert "Ajustei" in reply


def test_confirm_offers_watch_update_instead_of_auto_push():
    """Mudança mid-week aplicada: NÃO empurra sozinho — a resposta INFORMA e
    anexa a oferta de atualizar o relógio (pro 'sim' seguinte sincronizar)."""

    repo, applier, c1, c2 = _patched(_proposal())

    with (
        c1,
        c2,
        patch(
            f"{MODULE}.watch_update_offer",
            return_value="\n\n⌚ Quer no relógio? Responde sim.",
        ) as mock_offer,
    ):

        reply = _resolve("pode aplicar")

    mock_offer.assert_called_once_with("renato")
    assert "Ajustei" in reply
    assert "relógio" in reply


def test_confirm_on_stale_week_explains_instead_of_applying():

    repo, applier, c1, c2 = _patched(_proposal(), applied=None)

    with c1, c2:

        reply = _resolve("sim")

    repo.clear.assert_called_once()
    assert "semana virou" in reply


def test_reject_clears_without_applying():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = _resolve("não, deixa quieto")

    applier.apply.assert_not_called()
    repo.clear.assert_called_once()
    assert "deixo como está" in reply


def test_unclear_keeps_proposal_pending():

    repo, applier, c1, c2 = _patched(_proposal())

    with c1, c2:

        reply = _resolve("e o longão de sábado?")

    assert reply is None
    applier.apply.assert_not_called()
    repo.clear.assert_not_called()


def test_refine_reproposes_with_original_plus_correction():
    """Bug do Renato: correção de escopo ('não é a semana, é o de amanhã') não
    descarta — re-propõe combinando o pedido ORIGINAL + a correção pelo mesmo
    fluxo, sem perder a intenção."""

    repo, applier, c1, c2 = _patched(
        _proposal(kind="negotiation", source_text="deixa livre pro relógio")
    )

    with (
        c1,
        c2,
        patch(
            "app.application.coach.conversation.negotiation_flow."
            "NegotiationFlow.handle",
            new=AsyncMock(return_value="NOVA PROPOSTA"),
        ) as mock_handle,
    ):

        reply = _resolve("não é a semana, é o de amanhã")

    # a proposta velha morreu e a nova foi montada pelo fluxo (forçado)
    repo.clear.assert_called_once_with("renato")
    assert reply == "NOVA PROPOSTA"
    combined = mock_handle.call_args.args[2]
    assert "deixa livre pro relógio" in combined  # pedido original preservado
    assert "amanhã" in combined                    # correção incorporada
    assert mock_handle.call_args.kwargs["force"] is True


def test_expired_proposal_is_cleared_and_ignored():

    old = now_local() - timedelta(hours=48)

    repo, applier, c1, c2 = _patched(_proposal(created=old))

    with c1, c2:

        reply = _resolve("sim")

    assert reply is None
    repo.clear.assert_called_once()
    applier.apply.assert_not_called()
