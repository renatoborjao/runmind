import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.planning.training_preference_engine import (
    TrainingPreferenceEngine,
)
from app.domain.entities.memory_entry import MemoryEntry

GEN_TEXT = "app.infrastructure.integrations.gemini.client.generate_text"


def _memory(entry_id: str = "m-1") -> MemoryEntry:

    return MemoryEntry(
        id=entry_id,
        category="preferencia",
        content="Prefere treinar de manhã",
        source="conversation",
        created_at="2026-07-01T10:00:00+00:00",
    )


def _extract(response_text: str, **overrides):

    mock_generate = AsyncMock(return_value=response_text)

    with patch(GEN_TEXT, new=mock_generate):

        kwargs = dict(
            runner_name="Renato",
            current_memories=[_memory()],
            recent_turns=[{"role": "user", "text": "oi coach"}],
            incoming_text="queria manter os treinos de semana em ate 50 min",
            plan_owned=True,
            training_days="Terça, Quinta, Sábado",
            objective="10 km abaixo de 50 min",
        )

        kwargs.update(overrides)

        result = asyncio.run(TrainingPreferenceEngine.extract(**kwargs))

        _, call_kwargs = mock_generate.call_args

        return result, call_kwargs


def test_durable_preference_is_parsed():

    result, kwargs = _extract(
        '{"durable": true, "category": "preferencia",'
        ' "content": "Prefere treinos de semana em até ~50 min a partir de 04/08",'
        ' "archive": ["m-1"],'
        ' "reply": "Anotado! Vou montar teus próximos planos assim. 💪"}'
    )

    assert result is not None
    assert result.category == "preferencia"
    assert "50 min" in result.content
    assert result.archive == ["m-1"]
    assert "Anotado" in result.reply

    # o prompt leva memórias atuais, contexto, a mensagem nova E os pilares do
    # onboarding (dias fixos + meta) pra a preferência ser complementar
    prompt = kwargs["contents"]
    assert "m-1 — [preferencia] Prefere treinar de manhã" in prompt
    assert "user: oi coach" in prompt
    assert "manter os treinos de semana em ate 50 min" in prompt
    assert "Terça, Quinta, Sábado" in prompt
    assert "10 km abaixo de 50 min" in prompt


def test_not_durable_returns_none():
    """Ajuste desta semana / pergunta: durable=false -> None (turno segue)."""

    result, _ = _extract('{"durable": false}')

    assert result is None


def test_invalid_category_is_rejected():
    """Categoria fora do conjunto (preferencia/disponibilidade) não passa —
    não gravamos memória com categoria inválida."""

    result, _ = _extract(
        '{"durable": true, "category": "lesao",'
        ' "content": "algo", "reply": "ok"}'
    )

    assert result is None


def test_missing_reply_or_content_is_rejected():

    result, _ = _extract(
        '{"durable": true, "category": "preferencia", "content": "x"}'
    )

    assert result is None


def test_malformed_json_returns_none():

    result, _ = _extract("isso nao e json {")

    assert result is None


def test_plan_owned_toggles_reply_guidance():
    """plan_owned muda a instrução de confirmação: com plano nosso, promete
    montar os próximos planos; sem (treinador externo), só anota."""

    _, owned = _extract('{"durable": false}', plan_owned=True)

    _, external = _extract('{"durable": false}', plan_owned=False)

    assert "proximos planos" in _strip(owned["contents"]) or (
        "próximos planos" in owned["contents"]
    )
    assert "treinador humano" in external["contents"]


def _strip(text: str) -> str:

    import unicodedata

    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
