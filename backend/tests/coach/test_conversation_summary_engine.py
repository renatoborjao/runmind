import asyncio
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

    mock_generate = AsyncMock(return_value=response_text or "")

    with patch(f"{MODULE}.generate_text", new=mock_generate):

        result = asyncio.run(
            ConversationSummaryEngine.summarize(
                runner_name="Renato",
                current_summary=current_summary,
                turns=TURNS,
            )
        )

        _, kwargs = mock_generate.call_args

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
