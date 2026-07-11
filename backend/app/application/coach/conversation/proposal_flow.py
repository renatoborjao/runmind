from datetime import datetime, timedelta

from app.application.coach.conversation.plan_change_applier import (
    PlanChangeApplier,
)
from app.application.coach.conversation.proposal_reply_detector import (
    ProposalReply,
    ProposalReplyDetector,
)
from app.core.clock import now_local
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

# proposta sem resposta por muito tempo caduca — não vale aplicar uma
# mudança que o atleta pediu ontem e esqueceu
PROPOSAL_TTL_HOURS = 24


class ProposalFlow:
    """Quando há uma proposta de mudança pendente, o próximo 'sim/não' do
    atleta a resolve: aceite aplica (e reconcilia o relógio), recusa descarta.
    Roda ANTES dos outros handlers — o 'sim' é resposta à proposta."""

    @staticmethod
    def resolve(
        profile: str,
        incoming_text: str,
    ) -> str | None:
        """Devolve a resposta ao atleta se resolveu a proposta; None se não
        havia proposta, ela caducou, ou a mensagem não é um sim/não claro
        (aí a conversa segue e a proposta continua pendente)."""

        repo = PlanProposalRepository()

        proposal = repo.load(profile)

        if proposal is None:

            return None

        if ProposalFlow._expired(proposal):

            repo.clear(profile)

            return None

        reply = ProposalReplyDetector.detect(incoming_text)

        if reply == ProposalReply.CONFIRM:

            return ProposalFlow._apply(profile, proposal, repo)

        if reply == ProposalReply.REJECT:

            repo.clear(profile)

            return (
                "Tranquilo, deixo como está. 👍 Qualquer hora a gente ajusta."
            )

        # não é sim nem não claro (contraproposta / mudou de assunto):
        # mantém a proposta pendente e deixa a conversa seguir
        return None

    @staticmethod
    def _apply(profile, proposal, repo) -> str:

        updated = PlanChangeApplier.apply(profile, proposal)

        repo.clear(profile)

        if updated is None:

            return (
                "Opa, sua semana virou e essa proposta já não vale mais. "
                "Me diz de novo o que você quer ajustar que eu remonto. 💪"
            )

        return (
            "Feito! Ajustei seu plano. 💪 Se você usa o relógio, já "
            "atualizei os treinos lá também."
        )

    @staticmethod
    def _expired(proposal) -> bool:

        try:

            created = datetime.fromisoformat(proposal.created_at)

        except (ValueError, TypeError):

            return True

        return now_local() - created > timedelta(hours=PROPOSAL_TTL_HOURS)
