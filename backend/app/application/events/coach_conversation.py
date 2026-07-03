from app.application.coach.conversation.coach_conversation_engine import (
    CoachConversationEngine,
)
from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
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
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)

MEMORY_EXTRACTION_CONTEXT_TURNS = 6

BUSY_REPLY = (
    "Opa, me embananei aqui por um instante 😅 "
    "Me manda sua mensagem de novo daqui a pouquinho?"
)


class CoachConversationEvent:

    @staticmethod
    async def execute(
        profile: str,
        incoming_text: str,
        sender_name: str = "",
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        repo = ConversationRepository()

        history = repo.recent_turns(profile)

        # indisponibilidade (Gemini/Strava fora do ar, rate limit)
        # não pode virar silêncio: o atleta sempre recebe resposta
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

        await NotificationService.send_training_feedback(
            phone=runner.phone,
            message=reply_text,
        )

        # A resposta já foi enviada: falha na memória nunca chega ao corredor.
        try:

            await CoachConversationEvent._update_memory(
                profile=profile,
                runner_name=runner.name,
                history=history,
                incoming_text=incoming_text,
            )

        except Exception as e:

            print(f"Falha ao atualizar memória de '{profile}': {e}")

        return reply_text

    @staticmethod
    async def _update_memory(
        profile: str,
        runner_name: str,
        history: list[dict],
        incoming_text: str,
    ) -> None:

        current_memories = RunnerMemoryRepository().active(profile)

        ops = await MemoryExtractionEngine.extract(
            runner_name=runner_name,
            current_memories=current_memories,
            recent_turns=history[-MEMORY_EXTRACTION_CONTEXT_TURNS:],
            incoming_text=incoming_text,
        )

        if ops["add"] or ops["archive"]:

            RunnerMemoryService.process(
                profile,
                ops,
            )
