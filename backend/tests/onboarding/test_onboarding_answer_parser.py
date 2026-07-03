import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.onboarding.onboarding_answer_parser import (
    OnboardingAnswerParser,
)

MODULE = "app.application.onboarding.onboarding_answer_parser"


def _parse(step: str, response_text: str | None):

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        mock_client = mock_client_cls.return_value

        mock_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text=response_text),
        )

        result = asyncio.run(
            OnboardingAnswerParser.parse(
                step=step,
                question="pergunta",
                answer="resposta do corredor",
            )
        )

        return result, mock_client


def test_parses_valid_json():

    result, mock_client = _parse(
        "ASK_BODY",
        '{"age": 33, "weight": 91.0, "height": 1.78}',
    )

    assert result == {"age": 33, "weight": 91.0, "height": 1.78}

    _, kwargs = mock_client.aio.models.generate_content.call_args
    assert kwargs["config"].response_mime_type == "application/json"
    assert "resposta do corredor" in kwargs["contents"]


def test_malformed_json_returns_empty():

    result, _ = _parse("ASK_NAME", "não sou json")

    assert result == {}


def test_none_response_returns_empty():

    result, _ = _parse("ASK_NAME", None)

    assert result == {}


def test_unknown_step_returns_empty_without_calling_gemini():

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        result = asyncio.run(
            OnboardingAnswerParser.parse(
                step="PASSO_INEXISTENTE",
                question="q",
                answer="a",
            )
        )

        assert result == {}

        mock_client_cls.assert_not_called()
