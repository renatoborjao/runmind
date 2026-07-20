from app.application.events.assistant_errors import (
    AssistantUnavailable,
)
from app.application.coach.conversation.coach_conversation_engine import (
    CoachConversationEngine,
)
from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
)
from app.application.coach.conversation.intent_router import (
    IntentRouter,
)
from app.application.coach.conversation.on_demand_answers import (
    OnDemandAnswers,
)
from app.application.coach.conversation.plan_preference_applier import (
    PlanPreferenceApplier,
)
from app.application.coach.conversation.plan_preference_detector import (
    PlanPreferenceDetector,
)
from app.application.coach.conversation.goal_change_applier import (
    GoalChangeApplier,
)
from app.application.coach.conversation.proposal_flow import ProposalFlow
from app.application.coach.conversation.aversion_flow import AversionFlow
from app.application.coach.conversation.negotiation_flow import NegotiationFlow
from app.application.coach.conversation.move_skip_flow import MoveSkipFlow
from app.application.garmin.garmin_sync import GarminSync
from app.application.coach.conversation.conversation_summary_engine import (
    ConversationSummaryEngine,
)
from app.application.coach.memory.memory_extraction_engine import (
    MemoryExtractionEngine,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.core.clock import use_athlete_timezone
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)

MEMORY_EXTRACTION_CONTEXT_TURNS = 6

# janela recente enviada ao Gemini; turnos além dela viram resumo
CONVERSATION_WINDOW = 20

# dobra o resumo em lotes: 1 chamada Gemini a cada ~10 turnos antigos
SUMMARY_BATCH_MIN = 10

# mensagens triviais ("ok", "sim", "valeu 💪") não têm fato durável:
# pular a extração de memória economiza 1 chamada Gemini por mensagem
MEMORY_EXTRACTION_MIN_CHARS = 12

BUSY_REPLY = (
    "Opa, me embananei aqui por um instante 😅 "
    "Me manda sua mensagem de novo daqui a pouquinho?"
)


class CoachUnavailable(AssistantUnavailable):
    """Especialização de [[AssistantUnavailable]] pra conversa do coach.
    Mesmo contrato: sinaliza pro webhook adiar e tentar de novo; só o
    último fôlego (send_fallback=True) manda o fallback."""


class CoachConversationEvent:

    @staticmethod
    async def execute(
        profile: str,
        incoming_text: str,
        sender_name: str = "",
        send_fallback: bool = True,
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        # todas as datas da conversa (hoje/amanhã, semana) no fuso do atleta
        use_athlete_timezone(runner.timezone)

        repo = ConversationRepository()

        history = repo.recent_turns(profile)

        # Perguntas com dado canônico ("como foi meu último treino?",
        # "qual meu próximo treino?") são respondidas de forma completa e
        # determinística, sem passar pelo Gemini (que resumia/desconfigurava).
        reply_text = None

        used_deterministic = False

        # Resposta a uma proposta pendente ("sim/não" a uma troca que o coach
        # ofereceu): resolve ANTES de tudo — o "sim" é resposta à proposta.
        try:

            reply_text = ProposalFlow.resolve(profile, incoming_text)

            used_deterministic = reply_text is not None

        except Exception as e:

            print(f"Falha ao resolver proposta de '{profile}': {e}")

            reply_text = None

        # "SIM" pra oferta de mandar os treinos pro Garmin (ou pedido
        # explícito "manda pro relógio") — sincroniza na hora, sem Gemini.
        if reply_text is None:

            try:

                reply_text = await GarminSync.handle_reply(
                    profile,
                    runner,
                    incoming_text,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(f"Falha no fluxo Garmin de '{profile}': {e}")

                reply_text = None

        # Pedido de mudança no plano ("longão no domingo") é aplicado de
        # verdade e na hora — determinístico, sem passar pelo Gemini.
        preference = (
            PlanPreferenceDetector.detect(incoming_text)
            if reply_text is None
            else None
        )

        if preference is not None:

            try:

                reply_text = await PlanPreferenceApplier.apply(
                    profile,
                    runner,
                    preference,
                )

                used_deterministic = True

            except Exception as e:

                print(
                    f"Falha ao aplicar preferência de plano de "
                    f"'{profile}': {e}"
                )

                reply_text = None

        # Pedido de trocar o OBJETIVO/meta ("quero mudar minha meta pra
        # sub-45", "meu objetivo agora é saúde"): aplicado de verdade e na
        # hora, igual preferência de plano — sem passar pelo Gemini de chat.
        if reply_text is None:

            try:

                reply_text = await GoalChangeApplier.handle(
                    profile,
                    runner,
                    incoming_text,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(f"Falha ao trocar objetivo de '{profile}': {e}")

                reply_text = None

        intent = (
            IntentRouter.detect(incoming_text)
            if reply_text is None
            else None
        )

        if intent is not None:

            try:

                reply_text = await OnDemandAnswers.answer(
                    intent,
                    profile,
                    runner,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(
                    f"Falha na resposta determinística ({intent}) "
                    f"para '{profile}': {e}"
                )

                reply_text = None

        # Pedido de mover/pular treino ("joga pra quarta" / "não treino hoje"):
        # o coach PROPÕE a mudança no plano e guarda pro "sim".
        if reply_text is None:

            try:

                reply_text = await MoveSkipFlow.handle(
                    profile,
                    runner,
                    incoming_text,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(f"Falha no fluxo de mover/pular de '{profile}': {e}")

                reply_text = None

        # Pedido de trocar/evitar um tipo de treino ("não curto tiro"): o
        # coach PROPÕE uma adaptação (mantendo o estímulo) e guarda pro "sim".
        if reply_text is None:

            try:

                reply_text = await AversionFlow.handle(
                    profile,
                    runner,
                    incoming_text,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(f"Falha no fluxo de aversão de '{profile}': {e}")

                reply_text = None

        # Negociação geral ("deixa mais leve", "quero mais rodagens"): o coach
        # remonta a semana com critério (segura o essencial da meta), mostra a
        # versão revisada e guarda pro 'sim'. Depois da aversão (tipo) e do
        # mover/pular (dia) — pega o que sobra.
        if reply_text is None:

            try:

                reply_text = await NegotiationFlow.handle(
                    profile,
                    runner,
                    incoming_text,
                )

                used_deterministic = reply_text is not None

            except Exception as e:

                print(f"Falha no fluxo de negociação de '{profile}': {e}")

                reply_text = None

        # indisponibilidade (Gemini/Strava fora do ar, rate limit)
        # não pode virar silêncio: o atleta sempre recebe resposta
        if reply_text is None:

            try:

                context_facts = await ConversationContextBuilder.build(
                    profile,
                )

                reply_text = await CoachConversationEngine.reply(
                    runner_name=runner.name,
                    context_facts=context_facts,
                    conversation_history=history,
                    incoming_text=incoming_text,
                )

            except Exception as e:

                print(f"Falha na conversa com '{profile}': {e}")

                # ainda há fôlego pra retry adiado: sinaliza pro webhook
                # tentar de novo em vez de mandar o fallback agora
                if not send_fallback:

                    raise CoachUnavailable(str(e)) from e

                reply_text = BUSY_REPLY

        repo.append_turn(
            profile,
            role="user",
            text=incoming_text,
        )

        repo.append_turn(
            profile,
            role="assistant",
            text=reply_text,
        )

        await NotificationService.send(
            runner,
            reply_text,
        )

        # A resposta já foi enviada: falha na memória nunca chega ao corredor.
        # Pergunta respondida por card (último/próximo treino) não carrega
        # fato durável — pula a extração e economiza uma chamada Gemini.
        if not used_deterministic:

            try:

                await CoachConversationEvent._update_memory(
                    profile=profile,
                    runner_name=runner.name,
                    history=history,
                    incoming_text=incoming_text,
                )

            except Exception as e:

                print(f"Falha ao atualizar memória de '{profile}': {e}")

        try:

            await CoachConversationEvent._update_summary(
                profile=profile,
                runner_name=runner.name,
                repo=repo,
            )

        except Exception as e:

            print(f"Falha ao atualizar resumo de '{profile}': {e}")

        return reply_text

    @staticmethod
    async def _update_summary(
        profile: str,
        runner_name: str,
        repo: ConversationRepository,
    ) -> None:
        """Dobra no resumo corrido os turnos que já saíram da janela
        recente e ainda não foram cobertos."""

        turns = repo.load(profile)

        outside_window = turns[:-CONVERSATION_WINDOW]

        if not outside_window:

            return

        summary_state = repo.load_summary(profile)

        covered_until = summary_state["covered_until"]

        pending = [
            turn
            for turn in outside_window
            if turn["timestamp"] > covered_until
        ]

        if len(pending) < SUMMARY_BATCH_MIN:

            return

        updated = await ConversationSummaryEngine.summarize(
            runner_name=runner_name,
            current_summary=summary_state["summary"],
            turns=pending,
        )

        repo.save_summary(
            profile,
            updated,
            pending[-1]["timestamp"],
        )

    @staticmethod
    async def _update_memory(
        profile: str,
        runner_name: str,
        history: list[dict],
        incoming_text: str,
    ) -> None:

        if len(incoming_text.strip()) < MEMORY_EXTRACTION_MIN_CHARS:

            return

        current_memories = RunnerMemoryRepository().active(profile)

        ops = await MemoryExtractionEngine.extract(
            runner_name=runner_name,
            current_memories=current_memories,
            recent_turns=history[-MEMORY_EXTRACTION_CONTEXT_TURNS:],
            incoming_text=incoming_text,
        )

        if ops["add"] or ops["archive"] or ops.get("race"):

            RunnerMemoryService.process(
                profile,
                ops,
            )
