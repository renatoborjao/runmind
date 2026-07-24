import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.memory.coach_learning_engine import (
    CoachLearningEngine,
)
from app.domain.entities.coach_learning import CoachLearning

GEN_JSON = "app.application.coach.memory.coach_learning_engine.generate_json"


def _learning(entry_id="cl-1") -> CoachLearning:

    return CoachLearning(
        id=entry_id,
        category="aderencia",
        content="Sempre cumpre o tiro curto",
        source="weekly_distillation",
        created_at="2026-07-01T10:00:00+00:00",
        expires_at="2026-09-01T10:00:00+00:00",
    )


def _extract(response, current=None, evidence="prescrito X, executou Y"):
    """Roda o engine com o generate_json mockado. `response` simula o que o
    parse devolveria — como o generate_json real chama parse internamente,
    mockamos ele pra devolver direto o dict de ops."""

    async def fake_generate_json(*, parse, contents, **_):

        # exercita o parser de verdade com o texto simulado
        return parse(response)

    with patch(GEN_JSON, new=AsyncMock(side_effect=fake_generate_json)):

        return asyncio.run(
            CoachLearningEngine.extract(
                "Renato",
                current or [_learning()],
                evidence,
            )
        )


def test_parses_add_reconfirm_archive():

    ops = _extract(
        '{"add": [{"category": "limite", "content": "Ponto ótimo é 3 dias"}],'
        ' "reconfirm": ["cl-1"], "archive": ["cl-2"]}'
    )

    assert ops["add"] == [
        {"category": "limite", "content": "Ponto ótimo é 3 dias"}
    ]
    assert ops["reconfirm"] == ["cl-1"]
    assert ops["archive"] == ["cl-2"]


def test_drops_unknown_category():

    ops = _extract(
        '{"add": [{"category": "inventada", "content": "x"},'
        ' {"category": "resposta", "content": "Recupera rápido"}]}'
    )

    assert ops["add"] == [
        {"category": "resposta", "content": "Recupera rápido"}
    ]


def test_drops_add_without_content():

    ops = _extract('{"add": [{"category": "aderencia"}]}')

    assert ops["add"] == []


def test_malformed_json_returns_none_for_regen():
    """parse devolve None em JSON torto pra o generate_json re-gerar."""

    result = CoachLearningEngine._parse_ops("isto não é json {{{")

    assert result is None


def test_empty_ops_when_generate_returns_none():
    """Se todas as tentativas falharem (generate_json devolve None), o engine
    devolve EMPTY_OPS — não quebra a destilação."""

    with patch(GEN_JSON, new=AsyncMock(return_value=None)):

        ops = asyncio.run(
            CoachLearningEngine.extract("Renato", [_learning()], "ev")
        )

    assert ops == {"add": [], "reconfirm": [], "archive": []}


def test_prompt_carries_learnings_and_evidence():
    """O prompt tem que levar os aprendizados atuais e a evidência da semana
    pro modelo raciocinar em cima do histórico."""

    captured = {}

    async def capture(*, contents, parse, **_):

        captured["prompt"] = contents

        return parse('{"add": [], "reconfirm": [], "archive": []}')

    with patch(GEN_JSON, new=AsyncMock(side_effect=capture)):

        asyncio.run(
            CoachLearningEngine.extract(
                "Renato",
                [_learning()],
                "Aderência: 2/3; mais fura o longão de domingo.",
            )
        )

    assert "Sempre cumpre o tiro curto" in captured["prompt"]
    assert "mais fura o longão de domingo" in captured["prompt"]
    assert "Renato" in captured["prompt"]
