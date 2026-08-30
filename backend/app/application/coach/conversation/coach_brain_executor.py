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
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
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

        CoachBrainExecutor._log(profile, incoming_text, pending, decision)

        # vigia de saúde: mede a taxa de fallback (cérebro devolvendo None) numa
        # janela rolante e alerta o dono se estourar — observabilidade ativa,
        # best-effort (nunca derruba a resposta). Ver [[project_roteador_acao_ia]].
        from app.application.monitoring.coach_brain_monitor import (
            CoachBrainMonitor,
        )

        await CoachBrainMonitor.record(fallback=decision is None)

        if decision is None:

            return None

        # 1) resposta a uma proposta PENDENTE
        if pending is not None and decision.on_pending:

            return await CoachBrainExecutor._resolve_pending(
                profile, runner, decision, pending, repo, incoming_text,
                context_facts,
            )

        # 2) pedido(s) de MUDANÇA no plano — uma OU VÁRIAS numa proposta só
        if decision.all_actions:

            applied = await CoachBrainExecutor._act_all(
                profile, runner, decision.all_actions, repo, incoming_text,
                context_facts,
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
        context_facts="",
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

        if decision.all_actions:

            applied = await CoachBrainExecutor._act_all(
                profile, runner, decision.all_actions, repo, incoming_text,
                context_facts,
            )

            if applied is not None:

                return applied

        return decision.say or (
            "Beleza, me diz de forma direta o que muda que eu remonto. 💪"
        )

    @staticmethod
    async def _act_all(
        profile, runner, actions: list[BrainAction], repo, incoming_text,
        context_facts="",
    ) -> str | None:
        """Executa a(s) ação(ões). DUAS+ mudanças de plano na mesma mensagem
        (ex.: "troca terça pra quarta E quinta pra sexta") viram UMA proposta
        combinada — nenhuma troca fica de fora (o bug do Renato). Uma ação (ou
        mistura rara com rotina/objetivo) segue o caminho de sempre."""

        proposal = [a for a in actions if a.type in _PROPOSAL_ACTIONS]

        if len(actions) >= 2 and len(proposal) == len(actions):

            return await CoachBrainExecutor._propose_multi(
                profile, runner, actions, repo, context_facts,
            )

        return await CoachBrainExecutor._act(
            profile, runner, actions[0], repo, incoming_text, context_facts,
        )

    @staticmethod
    async def _act(
        profile, runner, action: BrainAction, repo, incoming_text,
        context_facts="",
    ) -> str | None:
        """Concretiza UMA ação: mudança da semana vira PROPOSTA (pede 'sim');
        rotina durável vira MEMÓRIA; objetivo/preferência os appliers aplicam.
        None se não deu."""

        if action.type in _PROPOSAL_ACTIONS:

            proposed = await CoachBrainExecutor._propose(
                profile, runner, action, repo, context_facts,
            )

            if proposed is not None:

                return proposed

            # TREINADOR EXTERNO: não editamos a semana dele (é do treinador) —
            # o _propose devolve None. Mas se ele quer um treino, MONTAMOS um
            # avulso pro dia da AÇÃO (o texto atual pode ser só "ok/monto?"),
            # nunca a promessa vazia "vou montar" (o coach fingindo). Bug real
            # do Mauricio. Ver [[project_treino_avulso]].
            if runner.external_coach and action.target_day:

                return await CoachBrainExecutor._one_off_for_day(
                    profile, runner, action.target_day, context_facts,
                )

            return None

        if action.type == "one_off":

            return await CoachBrainExecutor._one_off(
                profile, runner, incoming_text, context_facts,
            )

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

        if action.type == "coach_switch":

            return await CoachBrainExecutor._coach_switch(profile, runner, action)

        if action.type == "shoe":

            return await CoachBrainExecutor._shoe(profile, runner, incoming_text)

        return None

    @staticmethod
    async def _shoe(profile, runner, incoming_text) -> str | None:
        """Contador de km por tênis: registra pares, define o do dia a dia,
        ensina o rodízio, corrige atribuição, aposenta ou responde a km — com os
        números EXATOS do armário. Ver [[project_tracker_tenis]]."""

        from app.application.shoes.shoe_command_engine import ShoeCommandEngine

        return await ShoeCommandEngine.handle(profile, runner, incoming_text)

    @staticmethod
    async def _coach_switch(
        profile, runner: RunnerProfile, action: BrainAction,
    ) -> str | None:
        """Troca de TREINADOR, nos dois sentidos. externo→NOSSO: liga o coach do
        Ritmind e JÁ monta o plano da semana (força a regeneração). nosso→
        EXTERNO: passa o comando pro treinador humano e explica como mandar o
        plano dele. No-op se já está no modo pedido (deixa a fala do coach).
        Ver [[project_treino_avulso]]."""

        to_external = "extern" in (action.instruction or "").lower()

        if to_external:

            if runner.external_coach:

                return None  # já é externo — nada a trocar

            RunnerProfileRepository().update_fields(
                profile, {"external_coach": True},
            )

            return (
                f"Fechado, {runner.name}! A partir de agora quem manda no plano "
                "é o teu treinador. 👊 Me manda uma foto (ou várias) do treino "
                "que ele montar, que eu registro, acompanho cada sessão e te dou "
                "o feedback completo — do jeito que você já conhece. Sigo aqui "
                "com você. 💪"
            )

        # externo -> NOSSO coach
        if not runner.external_coach:

            return None  # já sou eu quem monta

        RunnerProfileRepository().update_fields(
            profile, {"external_coach": False},
        )

        # regenera a semana com o NOSSO motor (o flag já está False no disco;
        # for_profile recarrega o perfil e gera de verdade)
        _, plan = await CurrentPlanProvider.for_profile(profile, force=True)

        plan_text = WeeklyPlanMessageFormatter.week_plan_message(
            runner.name, plan, profile=profile,
        )

        # semana nova gerada -> oferece mandar pro relógio (o 'sim' empurra; o
        # lembrete cobre se ele não responder). watch_update_offer se auto-anula
        # se ele nunca sincronizou antes (sem ruído).
        return (
            f"Que honra, {runner.name}! A partir de agora EU cuido do teu "
            "treino. 🙌 Vou montar cada semana ancorado no teu histórico, no teu "
            "corpo e na tua meta — e evoluindo contigo. Bora começar: aqui está "
            f"teu plano desta semana. 💪\n\n{plan_text}{watch_update_offer(profile)}"
        )

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
    async def _one_off(profile, runner, incoming_text, context_facts="") -> str | None:
        """Treino AVULSO pra um dia que o plano não cobre ("monta um treino pra
        domingo") — monta UMA sessão ancorada no histórico/evolução do atleta e
        oferece o relógio. Roteia pro fluxo especialista SEM o portão de
        palavra-chave (o cérebro já reconheceu). None se não deu (cai na fala)."""

        from app.application.coach.conversation.one_off_workout_flow import (
            OneOffWorkoutFlow,
        )

        return await OneOffWorkoutFlow.build_for(
            profile, runner, incoming_text, athlete_context=context_facts,
        )

    @staticmethod
    async def _one_off_for_day(
        profile, runner, target_day: str, context_facts="",
    ) -> str | None:
        """Treino avulso pra um DIA explícito (o dia da ação do cérebro), sem
        depender do texto atual (que pode ser só "ok"/"monto?"). Sintetiza o
        pedido com o dia e roteia pro fluxo avulso."""

        from app.core.weekdays import weekday_label

        request = f"monta um treino pra {weekday_label(target_day)}"

        return await CoachBrainExecutor._one_off(
            profile, runner, request, context_facts,
        )

    @staticmethod
    async def _propose(
        profile, runner, action: BrainAction, repo, context_facts="",
    ) -> str | None:
        """Monta a proposta (move/skip via MoveSkipEngine; adjust/simplify via
        NegotiationEngine) COM ESCOPO, guarda pendente e devolve o preview.
        Pedido COMPOSTO (mover de dia E mudar o conteúdo) vira UMA proposta só:
        move + ajuste da sessão movida. O ajuste passa pela base completa do
        atleta (context_facts) — nunca no vácuo."""

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
                    context_facts,
                )

                if combined is not None:

                    operations, message = combined

        else:  # adjust | simplify

            negotiation = await NegotiationEngine.propose(
                runner, plan, request_text, athlete_context=context_facts,
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
    async def _propose_multi(
        profile, runner, actions: list[BrainAction], repo, context_facts="",
    ) -> str | None:
        """VÁRIAS mudanças da mesma mensagem numa proposta ÚNICA. Cada ação é
        calculada sobre o plano JÁ com as anteriores aplicadas (um plano-espelho
        que evolui) — então a 2ª troca enxerga a 1ª e o descanso entre elas fica
        certo. Junta todas as operações, monta UM 'como fica' e guarda UMA
        pendente. None se nenhuma vingou (cai na fala do coach)."""

        _, plan = await CurrentPlanProvider.for_profile(profile)

        if not plan.sessions or plan.source == "externo":

            return None

        mirror = copy.deepcopy(plan)

        all_ops: list[dict] = []

        leads: list[str] = []

        for action in actions:

            result = await CoachBrainExecutor._ops_for_action(
                runner, mirror, action, context_facts,
            )

            if result is None:

                continue

            ops, lead = result

            if not ops:

                continue

            PlanChangeApplier._apply_operations(mirror, ops)

            all_ops.extend(ops)

            if lead:

                leads.append(lead)

        if not all_ops:

            return None

        message = CoachBrainExecutor._revised_message(
            plan, all_ops, CoachBrainExecutor._join_leads(runner.name, leads),
        )

        repo.save(
            profile,
            PlanProposal(
                kind="multi",
                week_start=plan.week_start.isoformat(),
                preview=message,
                created_at=now_local().isoformat(),
                operations=all_ops,
            ),
        )

        return message

    @staticmethod
    async def _ops_for_action(
        runner, plan, action: BrainAction, context_facts="",
    ) -> tuple[list[dict], str] | None:
        """Operações + um LEAD curto de UMA ação sobre `plan` (o espelho já
        evoluído). Move/skip via MoveSkipEngine (com composto move+conteúdo);
        adjust/simplify via NegotiationEngine. None se a ação não vingou."""

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

            if (
                action.type == "move"
                and action.content_change
                and request.target_day
            ):

                combined = await CoachBrainExecutor._move_and_adjust(
                    runner, plan, operations, request, action.content_change,
                    context_facts,
                )

                if combined is not None:

                    operations, _ = combined

                    return operations, CoachBrainExecutor._move_lead(
                        request, adjusted=True,
                    )

            return operations, CoachBrainExecutor._move_lead(request)

        negotiation = await NegotiationEngine.propose(
            runner, plan, request_text, athlete_context=context_facts,
        )

        if negotiation is None:

            return None

        return negotiation.operations, negotiation.message

    @staticmethod
    def _move_lead(request, adjusted: bool = False) -> str:
        """Frase curta de UMA troca/pulo pro cabeçalho da proposta combinada."""

        from app.core.weekdays import weekday_label

        if request.action == "skip":

            return f"tiro o de {weekday_label(request.day)}"

        base = f"{weekday_label(request.day)} → {weekday_label(request.target_day)}"

        return f"{base} (conteúdo ajustado)" if adjusted else base

    @staticmethod
    def _join_leads(name: str, leads: list[str]) -> str:

        if not leads:

            return f"Beleza, {name}! Ajustando teus treinos:"

        return f"Beleza, {name}! Ajustando: {'; '.join(leads)}."

    @staticmethod
    async def _move_and_adjust(
        runner, plan, move_ops: list[dict], request, content_change: str,
        context_facts="",
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
            runner, post_move, adjust_text, athlete_context=context_facts,
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
    def _log(profile, incoming_text, pending, decision) -> None:
        """Registra a decisão do cérebro (modo observação). Best-effort: falhar
        aqui NUNCA pode derrubar a conversa."""

        try:

            from app.core.clock import now_local
            from app.infrastructure.persistence.coach_brain_log_repository import (
                CoachBrainLogRepository,
            )

            entry = {
                "ts": now_local().isoformat(timespec="seconds"),
                "incoming": (incoming_text or "")[:200],
                "pending": pending is not None,
                "fallback": decision is None,
            }

            if decision is not None:

                entry["say"] = (decision.say or "")[:200]

                entry["card"] = decision.answer_card

                entry["on_pending"] = decision.on_pending

                if decision.all_actions:

                    entry["actions"] = [
                        {
                            "type": a.type,
                            "scope": a.scope,
                            "target_day": a.target_day,
                            "content_change": a.content_change,
                        }
                        for a in decision.all_actions
                    ]

            CoachBrainLogRepository().record(profile, entry)

        except Exception as e:

            print(f"Log do cérebro falhou p/ '{profile}': {e}")

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
