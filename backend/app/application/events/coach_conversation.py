from app.application.coach.conversation.coach_conversation_engine import (
    CoachConversationEngine,
)
from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
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


class CoachConversationEvent:

    @staticmethod
    async def execute(
        profile: str,
        incoming_text: str,
        sender_name: str = "",
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        context_facts = await ConversationContextBuilder.build(profile)

        repo = ConversationRepository()

        history = repo.recent_turns(profile)

        reply_text = await CoachConversationEngine.reply(
            runner_name=runner.name,
            context_facts=context_facts,
            conversation_history=history,
            incoming_text=incoming_text,
        )

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

        return reply_text
