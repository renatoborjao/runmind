import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.coach_conversation_engine import (
    SYSTEM_PROMPT_TEMPLATE,
    CoachConversationEngine,
)

MODULE = "app.application.coach.conversation.coach_conversation_engine"


def test_reply_builds_system_and_contents_and_returns_text():

    with patch(f"{MODULE}.generate_text") as mock_generate:

        mock_generate.return_value = "Bom dia, Renato! Vamos com tudo hoje."

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

        _, kwargs = mock_generate.call_args

        assert "Renato" in kwargs["config"].system_instruction
        assert "Volume semanal atual: 30.0 km" in kwargs["config"].system_instruction

        # chat com o atleta: resposta vazia não pode virar mensagem em branco
        assert kwargs["require_text"] is True

        assert kwargs["contents"] == [
            {"role": "user", "parts": [{"text": "Oi coach"}]},
            {"role": "model", "parts": [{"text": "Oi, Renato!"}]},
            {"role": "user", "parts": [{"text": "Como foi meu treino de ontem?"}]},
        ]


def test_reply_propagates_failure_so_caller_can_fall_back():

    # generate_text já esgotou os retries (ex: resposta sempre vazia);
    # o engine deixa a exceção subir para o CoachConversationEvent decidir
    # o fallback — melhor que devolver "" e mandar mensagem em branco.
    with patch(f"{MODULE}.generate_text") as mock_generate:

        mock_generate.side_effect = RuntimeError("Gemini indisponível")

        raised = False

        try:

            asyncio.run(
                CoachConversationEngine.reply(
                    runner_name="Renato",
                    context_facts="",
                    conversation_history=[],
                    incoming_text="oi",
                )
            )

        except RuntimeError:

            raised = True

        assert raised


def test_system_prompt_contains_non_negotiable_guardrails():

    assert "NUNCA decide" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA dá conselho médico" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA inventa números" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA afirma ter executado" in SYSTEM_PROMPT_TEMPLATE
    assert "desculpa técnica falsa" in SYSTEM_PROMPT_TEMPLATE
