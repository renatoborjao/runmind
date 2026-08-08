from datetime import datetime, timedelta

from app.application.coach.conversation.plan_change_applier import (
    PlanChangeApplier,
)
from app.application.coach.conversation.proposal_reply_detector import (
    ProposalReply,
    ProposalReplyDetector,
)
from app.application.coach.memory.coaching_signal_recorder import (
    CoachingSignalRecorder,
)
from app.application.garmin.watch_offer import watch_update_offer
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
    async def resolve(
        profile: str,
        runner,
        incoming_text: str,
    ) -> str | None:
        """Resolve a proposta pendente: aceite aplica, recusa descarta,
        CORREÇÃO re-propõe (não descarta), e mudança de assunto deixa seguir.
        None se não havia proposta ou caducou."""

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

        if reply == ProposalReply.REFINE:

            return await ProposalFlow._refine(
                profile, runner, proposal, incoming_text, repo
            )

        # mudou de assunto: mantém a proposta pendente e deixa a conversa seguir
        return None

    @staticmethod
    async def _refine(profile, runner, proposal, correction, repo) -> str | None:
        """O atleta corrigiu a proposta ("não é a semana, é o de amanhã"). NÃO
        descarta cegamente: re-propõe combinando o pedido ORIGINAL + a correção,
        pelo mesmo fluxo que gerou a proposta. Assim o refino mantém a intenção
        e ajusta o escopo. Bug real do Renato (correção virava 'não')."""

        original = (proposal.source_text or "").strip()

        combined = (
            f"{original} (correção do atleta: {correction})"
            if original
            else correction
        )

        # a proposta velha morre; o fluxo re-rodado grava a nova
        repo.clear(profile)

        # importa aqui pra evitar ciclo de import
        from app.application.coach.conversation.aversion_flow import (
            AversionFlow,
        )
        from app.application.coach.conversation.move_skip_flow import (
            MoveSkipFlow,
        )
        from app.application.coach.conversation.negotiation_flow import (
            NegotiationFlow,
        )

        if proposal.kind in ("move", "skip"):

            new_message = await MoveSkipFlow.handle(
                profile, runner, combined, force=True
            )

        elif proposal.kind == "aversion":

            new_message = await AversionFlow.handle(
                profile, runner, combined, force=True
            )

        else:

            new_message = await NegotiationFlow.handle(
                profile, runner, combined, force=True
            )

        if new_message:

            return new_message

        # não deu pra remontar com a correção: honesto, sem fingir
        return (
            "Beleza, não vou aplicar a versão anterior. Me diz de forma "
            "direta o que você quer mudar (ex.: 'deixa só o treino de amanhã "
            "num ritmo leve') que eu remonto. 💪"
        )

    @staticmethod
    def _apply(profile, proposal, repo) -> str:

        updated = PlanChangeApplier.apply(profile, proposal)

        repo.clear(profile)

        if updated is None:

            return (
                "Opa, sua semana virou e essa proposta já não vale mais. "
                "Me diz de novo o que você quer ajustar que eu remonto. 💪"
            )

        # Fonte A do cérebro coach: o atleta ACEITOU uma correção — sinal de
        # alta qualidade pra destilação de domingo. Best-effort: registrar
        # nunca pode derrubar a aplicação da proposta (que já aconteceu).
        try:

            CoachingSignalRecorder.record(
                profile,
                kind=f"aceitou_{proposal.kind}",
                detail=proposal.preview,
            )

        except Exception as e:

            print(f"Falha ao registrar sinal de aprendizado '{profile}': {e}")

        # mudança mid-week: NÃO empurra sozinho — informa e PERGUNTA se quer
        # atualizar o relógio (o 'sim' seguinte sincroniza). Domingo é auto.
        return "Feito! Ajustei seu plano. 💪" + watch_update_offer(profile)

    @staticmethod
    def _expired(proposal) -> bool:

        try:

            created = datetime.fromisoformat(proposal.created_at)

        except (ValueError, TypeError):

            return True

        return now_local() - created > timedelta(hours=PROPOSAL_TTL_HOURS)
