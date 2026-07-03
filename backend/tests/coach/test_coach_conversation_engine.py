import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.coach_conversation_engine import (
    SYSTEM_PROMPT_TEMPLATE,
    CoachConversationEngine,
)

MODULE = "app.application.coach.conversation.coach_conversation_engine"


def _mock_response(text: str | None):

    return SimpleNamespace(text=text)


def test_reply_builds_system_and_contents_and_returns_text():

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        mock_client = mock_client_cls.return_value

        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("Bom dia, Renato! Vamos com tudo hoje."),
        )

        reply = asyncio.run(
            CoachConversationEngine.reply(
                runner_name="Renato",
                context_facts="Volume semanal atual: 30.0 km",
                conversation_history=[
                    {"role": "user", "text": "Oi coach"},
                    {"role": "assistant", "text": "Oi, Renato!"},
                ],
                incoming_text="Como foi meu treino de ontem?",
            )
        )

        assert reply == "Bom dia, Renato! Vamos com tudo hoje."

        _, kwargs = mock_client.aio.models.generate_content.call_args

        assert "Renato" in kwargs["config"].system_instruction
        assert "Volume semanal atual: 30.0 km" in kwargs["config"].system_instruction

        assert kwargs["contents"] == [
            {"role": "user", "parts": [{"text": "Oi coach"}]},
            {"role": "model", "parts": [{"text": "Oi, Renato!"}]},
            {"role": "user", "parts": [{"text": "Como foi meu treino de ontem?"}]},
        ]


def test_reply_returns_empty_string_when_no_text():

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        mock_client = mock_client_cls.return_value

        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(None),
        )

        reply = asyncio.run(
            CoachConversationEngine.reply(
                runner_name="Renato",
                context_facts="",
                conversation_history=[],
                incoming_text="oi",
            )
        )

        assert reply == ""


def test_system_prompt_contains_non_negotiable_guardrails():

    assert "NUNCA decide" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA dá conselho médico" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA inventa números" in SYSTEM_PROMPT_TEMPLATE
