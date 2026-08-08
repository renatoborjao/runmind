"""Executa a decisão do CoachBrain com as "mãos" determinísticas.

O cérebro DECIDE (na voz do coach); aqui a gente EXECUTA de verdade: renderiza o
cartão EXATO (sem desconfigurar número), monta a proposta de mudança COM ESCOPO
(uma sessão × semana) e guarda pro "sim", aplica a pendência + oferece o relógio,
ou só devolve a fala do coach. Nada é fingido — toda ação é real.

Devolve o texto pro atleta, ou None se não deu pra concretizar (o chamador cai
na cascata determinística — nunca silêncio). Ver [[project_roteador_acao_ia]]."""

import copy

from app.application.coach.conversation.coach_brain import (
    BrainAction,
    BrainDecision,
    CoachBrain,
)
from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
)
from app.application.coach.conversation.move_skip_flow import MoveSkipFlow
from app.application.coach.conversation.on_demand_answers import OnDemandAnswers
from app.application.coach.conversation.plan_change_applier import (
    PlanChangeApplier,
)
from app.application.coach.planning.move_skip_engine import MoveSkipEngine
from app.application.coach.planning.negotiation_engine import NegotiationEngine
from app.application.garmin.watch_offer import watch_update_offer
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.core.clock import now_local, today_local
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

# cartão do cérebro -> intent determinístico do OnDemandAnswers
_CARD_TO_INTENT = {
    "weekly_plan": "WEEKLY_PLAN",
    "next_training": "NEXT_TRAINING",
    "last_training": "LAST_TRAINING",
    "body": "BODY_READING",
    "fitness": "FITNESS_TREND",
    "paces": "PACE_ZONES",
    "sleep": "SLEEP",
    "race": "RACE_STRATEGY",
    "portrait": "STATE_PORTRAIT",
    "help": "HELP",
}

# ações que viram PROPOSTA (pedem "sim") vs. as que os appliers já aplicam
_PROPOSAL_ACTIONS = {"move", "skip", "adjust", "simplify"}


class CoachBrainExecutor:

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
        conversation_history: list[dict] | None = None,
    ) -> str | None:
        """Caminho do cérebro do coach. None => cai na cascata determinística."""

        context_facts = await ConversationContextBuilder.build(
            profile, incoming_text=incoming_text,
        )

        repo = PlanProposalRepository()

        pending = repo.load(profile)

        decision = await CoachBrain.decide(
            runner_name=runner.name,
            context_facts=context_facts,
            incoming_text=incoming_text,
            pending_preview=pending.preview if pending else None,
            conversation_history=conversation_history,
        )

        if decision is None:

            return None

        # 1) resposta a uma proposta PENDENTE
        if pending is not None and decision.on_pending:

            return await CoachBrainExecutor._resolve_pending(
                profile, runner, decision, pending, repo, incoming_text,
            )

        # 2) pedido de MUDANÇA no plano
        if decision.action is not None:

            applied = await CoachBrainExecutor._act(
                profile, runner, decision, repo, incoming_text,
            )

            if applied is not None:

                return applied

            # não deu pra concretizar a ação: cai na fala do coach, se houver

        # 3) resposta com CARTÃO exato (dado denso), emoldurada pela voz do coach
        if decision.answer_card:

            card = await CoachBrainExecutor._render_card(
                decision.answer_card, profile, runner,
            )

            if card:

                return f"{decision.say}\n\n{card}" if decision.say else card

        # 4) só a fala do coach (conversa/dúvida/relato)
        return decision.say or None

    # ==================================================================

    @staticmethod
    async def _resolve_pending(
        profile, runner, decision: BrainDecision, pending, repo, incoming_text,
    ) -> str | None:

        if decision.on_pending == "apply":

            updated = PlanChangeApplier.apply(profile, pending)

            repo.clear(profile)

            if updated is None:

                return (
                    "Opa, tua semana virou e essa proposta já não vale mais. "
                    "Me diz de novo o que quer ajustar que eu remonto. 💪"
                )

            confirm = decision.say or "Feito! Ajustei seu plano. 💪"

            return confirm + watch_update_offer(profile)

        if decision.on_pending == "reject":

            repo.clear(profile)

            return decision.say or (
                "Tranquilo, deixo como está. 👍 Qualquer hora a gente ajusta."
            )

        # refine: descarta a velha e re-propõe com a correção (a ação já veio
        # corrigida do cérebro, com o escopo certo)
        repo.clear(profile)

        if decision.action is not None:

            applied = await CoachBrainExecutor._act(
                profile, runner, decision, repo, incoming_text,
            )

            if applied is not None:

                return applied

        return decision.say or (
            "Beleza, me diz de forma direta o que muda que eu remonto. 💪"
        )

    @staticmethod
    async def _act(
        profile, runner, decision: BrainDecision, repo, incoming_text,
    ) -> str | None:
        """Concretiza a ação: mudanças da semana viram PROPOSTA (pedem 'sim');
        rotina durável vira MEMÓRIA; objetivo/preferência os appliers aplicam.
        None se não deu."""

        action = decision.action

        if action.type in _PROPOSAL_ACTIONS:

            return await CoachBrainExecutor._propose(profile, runner, decision, repo)

        if action.type == "routine":

            return await CoachBrainExecutor._routine(profile, runner, incoming_text)

        if action.type == "goal":

            from app.application.coach.conversation.goal_change_applier import (
                GoalChangeApplier,
            )

            return await GoalChangeApplier.handle(
                profile, runner, action.instruction or action.type,
            )

        if action.type == "preference":

            return await CoachBrainExecutor._preference(profile, runner, action)

        return None

    @staticmethod
    async def _routine(profile, runner, incoming_text) -> str | None:
        """Preferência DURÁVEL de rotina: destila pra memória evolutiva (que já
        alimenta a geração do plano) via o motor especialista. None se a IA
        concluir que não é durável (cai na fala do coach)."""

        from app.application.coach.conversation.training_preference_flow import (
            TrainingPreferenceFlow,
        )

        return await TrainingPreferenceFlow.apply_preference(
            profile, runner, incoming_text,
        )

    @staticmethod
    async def _propose(
        profile, runner, decision: BrainDecision, repo,
    ) -> str | None:
        """Monta a proposta (move/skip via MoveSkipEngine; adjust/simplify via
        NegotiationEngine) COM ESCOPO, guarda pendente e devolve o preview.
        Pedido COMPOSTO (mover de dia E mudar o conteúdo) vira UMA proposta só:
        move + ajuste da sessão movida."""

        action = decision.action

        _, plan = await CurrentPlanProvider.for_profile(profile)

        if not plan.sessions or plan.source == "externo":

            return None

        request_text = CoachBrainExecutor._action_text(action)

        if action.type in ("move", "skip"):

            request = await MoveSkipEngine.propose(
                runner, plan, request_text, today_local(),
            )

            if request is None:

                return None

            operations = MoveSkipFlow._operations(plan, request)

            if not operations:

                return None

            message, kind = request.message, request.action

            # composto: mover E mudar o conteúdo do treino movido, numa tacada
            if (
                action.type == "move"
                and action.content_change
                and request.target_day
            ):

                combined = await CoachBrainExecutor._move_and_adjust(
                    runner, plan, operations, request, action.content_change,
                )

                if combined is not None:

                    operations, message = combined

        else:  # adjust | simplify

            negotiation = await NegotiationEngine.propose(
                runner, plan, request_text,
            )

            if negotiation is None:

                return None

            operations, kind = negotiation.operations, "negotiation"

            message = CoachBrainExecutor._revised_message(
                plan, operations, negotiation.message,
            )

        repo.save(
            profile,
            PlanProposal(
                kind=kind,
                week_start=plan.week_start.isoformat(),
                preview=message,
                created_at=now_local().isoformat(),
                operations=operations,
            ),
        )

        return message

    @staticmethod
    async def _move_and_adjust(
        runner, plan, move_ops: list[dict], request, content_change: str,
    ) -> tuple[list[dict], str] | None:
        """Composto: sobre o plano JÁ movido, ajusta o CONTEÚDO da sessão que
        mudou de dia (escopo = o dia de destino) e devolve (operações
        combinadas, preview). None se o ajuste não vingar — aí o chamador segue
        só com o move."""

        post_move = copy.deepcopy(plan)

        PlanChangeApplier._apply_operations(post_move, move_ops)

        adjust_text = CoachBrainExecutor._action_text(
            BrainAction(
                type="adjust",
                scope="single_session",
                target_day=request.target_day,
                instruction=content_change,
            )
        )

        negotiation = await NegotiationEngine.propose(
            runner, post_move, adjust_text,
        )

        if negotiation is None:

            return None

        # move (tira do dia de origem, põe no destino) + ajuste do conteúdo no
        # destino, aplicados em sequência: o último replace do destino vence
        operations = move_ops + negotiation.operations

        from app.core.weekdays import weekday_label

        lead = (
            f"Movo teu treino de {weekday_label(request.day)} pra "
            f"{weekday_label(request.target_day)} e já ajusto o conteúdo. "
            f"{negotiation.message}"
        )

        return operations, CoachBrainExecutor._revised_message(
            plan, operations, lead,
        )

    @staticmethod
    def _revised_message(plan, operations: list[dict], lead: str) -> str:
        """Aplica as operações num plano-espelho e monta o preview padrão
        ('como fica' + pedido de confirmação) — sem tocar no plano real."""

        preview_plan = copy.deepcopy(plan)

        PlanChangeApplier._apply_operations(preview_plan, operations)

        revised = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(preview_plan)
        ).strip()

        return (
            f"{lead}\n\n📋 Como fica:\n\n{revised}\n\n"
            "Posso aplicar? (responde *sim* ou *não*)"
        )

    @staticmethod
    async def _preference(profile, runner, action: BrainAction) -> str | None:

        from app.application.coach.conversation.plan_preference_applier import (
            PlanPreferenceApplier,
        )
        from app.application.coach.conversation.plan_preference_detector import (
            PlanPreference,
        )

        if not action.target_day:

            return None

        return await PlanPreferenceApplier.apply(
            profile, runner, PlanPreference(long_run_day=action.target_day),
        )

    @staticmethod
    def _action_text(action: BrainAction) -> str:
        """Sintetiza o pedido pro engine, carregando o ESCOPO (o engine é
        scope-aware: 'só o treino de <dia>' muda só aquela sessão)."""

        parts = [action.instruction or action.type]

        if action.scope == "single_session" and action.target_day:

            from app.core.weekdays import weekday_label

            parts.append(f"(só o treino de {weekday_label(action.target_day)})")

        return " ".join(parts).strip()

    @staticmethod
    async def _render_card(card: str, profile, runner) -> str | None:

        from app.application.coach.conversation.intent_router import ChatIntent

        intent_name = _CARD_TO_INTENT.get(card)

        if intent_name is None:

            return None

        try:

            return await OnDemandAnswers.answer(
                ChatIntent(intent_name), profile, runner,
            )

        except Exception as e:

            print(f"Cartão '{card}' falhou p/ '{profile}': {e}")

            return None
