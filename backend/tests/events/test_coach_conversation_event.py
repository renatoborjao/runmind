import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.events.coach_conversation import (
    CoachConversationEvent,
)
from tests.coach.factories import make_runner

MODULE = "app.application.events.coach_conversation"


def test_execute_orchestrates_context_reply_persistence_and_notification():

    runner = make_runner(name="Renato", phone="+5511975658679")

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.ConversationContextBuilder") as mock_context_builder,
        patch(f"{MODULE}.ConversationRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEngine") as mock_engine,
        patch(f"{MODULE}.NotificationService") as mock_notification,
    ):

        mock_load_runner.execute.return_value = runner

        mock_context_builder.build = AsyncMock(
            return_value="Volume semanal atual: 30.0 km",
        )

        mock_repo = MagicMock()
        mock_repo.recent_turns.return_value = [
            {"role": "user", "text": "oi"},
        ]
        mock_repo_cls.return_value = mock_repo

        mock_engine.reply = AsyncMock(
            return_value="Bom dia! Foi um baita treino ontem.",
        )

        mock_notification.send_training_feedback = AsyncMock()

        reply = asyncio.run(
            CoachConversationEvent.execute(
                profile="renato",
                incoming_text="Como foi meu treino de ontem?",
                sender_name="Renato",
            )
        )

        assert reply == "Bom dia! Foi um baita treino ontem."

        mock_load_runner.execute.assert_called_once_with("renato")

        mock_context_builder.build.assert_awaited_once_with("renato")

        mock_engine.reply.assert_awaited_once_with(
            runner_name="Renato",
            context_facts="Volume semanal atual: 30.0 km",
            conversation_history=[{"role": "user", "text": "oi"}],
            incoming_text="Como foi meu treino de ontem?",
        )

        assert mock_repo.append_turn.call_count == 2

        mock_repo.append_turn.assert_any_call(
            "renato",
            role="user",
            text="Como foi meu treino de ontem?",
        )

        mock_repo.append_turn.assert_any_call(
            "renato",
            role="assistant",
            text="Bom dia! Foi um baita treino ontem.",
        )

        mock_notification.send_training_feedback.assert_awaited_once_with(
            phone="+5511975658679",
            message="Bom dia! Foi um baita treino ontem.",
        )
