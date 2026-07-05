import asyncio
from unittest.mock import AsyncMock, patch

from app.application.onboarding.onboarding_answer_parser import (
    OnboardingAnswerParser,
)

MODULE = "app.application.onboarding.onboarding_answer_parser"

# frases livres que o parser determinístico NÃO resolve, forçando o
# fallback do Gemini (o que estes testes exercitam).
FREEFORM_ANSWER = "quero muito melhorar bastante nas corridas neste ano"


def _parse(step: str, response_text: str | None, answer=FREEFORM_ANSWER):

    mock_generate = AsyncMock(return_value=response_text or "")

    with patch(f"{MODULE}.generate_text", new=mock_generate):

        result = asyncio.run(
            OnboardingAnswerParser.parse(
                step=step,
                question="pergunta",
                answer=answer,
            )
        )

        return result, mock_generate


def test_parses_valid_json_via_gemini_fallback():

    result, mock_generate = _parse(
        "ASK_GOAL",
        '{"goal": "10 km Sub 55"}',
    )

    assert result == {"goal": "10 km Sub 55"}

    _, kwargs = mock_generate.call_args
    assert kwargs["config"].response_mime_type == "application/json"
    assert FREEFORM_ANSWER in kwargs["contents"]


def test_malformed_json_returns_empty():

    result, _ = _parse("ASK_GOAL", "não sou json")

    assert result == {}


def test_none_response_returns_empty():

    result, _ = _parse("ASK_GOAL", None)

    assert result == {}


def test_unknown_step_returns_empty_without_calling_gemini():

    mock_generate = AsyncMock(return_value="")

    with patch(f"{MODULE}.generate_text", new=mock_generate):

        result = asyncio.run(
            OnboardingAnswerParser.parse(
                step="PASSO_INEXISTENTE",
                question="q",
                answer="a",
            )
        )

        assert result == {}

        mock_generate.assert_not_awaited()


def test_deterministic_step_skips_gemini():

    # "sim" no passo do Strava é resolvido localmente — Gemini nem é chamado
    mock_generate = AsyncMock(return_value="")

    with patch(f"{MODULE}.generate_text", new=mock_generate):

        result = asyncio.run(
            OnboardingAnswerParser.parse(
                step="ASK_STRAVA",
                question="pergunta",
                answer="sim, já tenho",
            )
        )

        assert result == {"has_strava": True}

        mock_generate.assert_not_awaited()
