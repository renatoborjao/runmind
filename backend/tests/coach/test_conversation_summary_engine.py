import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.conversation_summary_engine import (
    ConversationSummaryEngine,
)

MODULE = (
    "app.application.coach.conversation.conversation_summary_engine"
)

TURNS = [
    {"role": "user", "text": "coach, como encaro a prova de outubro?"},
    {"role": "assistant", "text": "Vamos de pace conservador na largada."},
]


def _summarize(response_text: str | None, current_summary=""):

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        mock_client = mock_client_cls.return_value

        mock_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text=response_text),
        )

        result = asyncio.run(
            ConversationSummaryEngine.summarize(
                runner_name="Renato",
                current_summary=current_summary,
                turns=TURNS,
            )
        )

        _, kwargs = mock_client.aio.models.generate_content.call_args

        return result, kwargs


def test_summarize_returns_updated_text_and_sends_context():

    result, kwargs = _summarize(
        "Discutiram estratégia para a prova de outubro.",
        current_summary="Resumo antigo.",
    )

    assert result == "Discutiram estratégia para a prova de outubro."

    prompt = kwargs["contents"]
    assert "Resumo antigo." in prompt
    assert "prova de outubro" in prompt
    assert "user: coach" in prompt


def test_empty_response_keeps_current_summary():

    result, _ = _summarize(None, current_summary="Resumo antigo.")

    assert result == "Resumo antigo."


def test_whitespace_response_keeps_current_summary():

    result, _ = _summarize("   ", current_summary="Resumo antigo.")

    assert result == "Resumo antigo."
