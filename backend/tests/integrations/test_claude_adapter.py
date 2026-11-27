import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from app.infrastructure.integrations.claude import adapter
from app.infrastructure.integrations.claude.adapter import (
    ClaudeUnsupported,
    build_messages,
    build_request,
    claude_model_for,
    grounding_shim,
    usage_shim,
)
from app.infrastructure.integrations.gemini import client as gemini_client

GEMINI = "app.infrastructure.integrations.gemini.client"


def _settings(**over):

    base = dict(
        ai_provider="claude",
        anthropic_api_key="",
        plan_model="gemini-3.1-pro-preview",
        claude_plan_model="claude-opus-5-5",
        claude_chat_model="claude-sonnet-5-5",
        claude_extract_model="claude-haiku-5-5",
        claude_plan_effort="high",
        google_api_key="",
    )

    base.update(over)

    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fake_settings():

    with patch.object(adapter, "get_settings", return_value=_settings()):

        yield


# ---- modelo e esforço por papel ------------------------------------------


def test_modelo_por_familia():

    assert claude_model_for("gemini-3.1-pro-preview") == ("claude-opus-5-5", "plan")
    assert claude_model_for("gemini-3.5-flash-lite") == ("claude-haiku-5-5", "extract")
    assert claude_model_for("gemini-3.6-flash") == ("claude-sonnet-5-5", "chat")


def test_plano_usa_opus_esforco_alto_e_fallback_de_recusa():

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=6000,
        thinking_config=types.ThinkingConfig(thinking_budget=1024),
    )

    req = build_request("gemini-3.1-pro-preview", "prompt", config)

    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "high"}
    assert req["max_tokens"] == 16_000
    assert req["fallbacks"] == "default"
    assert "JSON" in req["system"]
    # nada que o Claude 5.5 rejeite
    for proibido in ("temperature", "top_p", "thinking", "tool_choice"):
        assert proibido not in req


def test_chat_esforco_segue_thinking_budget():

    low = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=256),
    )

    mid = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=1024),
    )

    assert build_request("gemini-3.6-flash", "x", low)["output_config"]["effort"] == "low"
    assert build_request("gemini-3.6-flash", "x", mid)["output_config"]["effort"] == "medium"


def test_haiku_sem_fallback_de_recusa():

    req = build_request("gemini-3.5-flash-lite", "x", types.GenerateContentConfig())

    assert "fallbacks" not in req and "betas" not in req


def test_max_tokens_tem_teto():

    config = types.GenerateContentConfig(max_output_tokens=200_000)

    assert build_request("gemini-3.6-flash", "x", config)["max_tokens"] == 64_000


# ---- conteúdo ------------------------------------------------------------


def test_conversa_gemini_vira_mensagens_claude():

    contents = [
        {"role": "model", "parts": [{"text": "Oi, sou o coach"}]},
        {"role": "user", "parts": [{"text": "oi"}]},
        {"role": "user", "parts": [{"text": "tudo bem?"}]},
        {"role": "model", "parts": [{"text": "Tudo!"}]},
        {"role": "user", "parts": [{"text": "e o treino?"}]},
    ]

    msgs = build_messages(contents)

    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
    # turnos seguidos do usuário fundidos
    assert [b["text"] for b in msgs[2]["content"]] == ["oi", "tudo bem?"]


def test_imagem_e_texto_viram_uma_mensagem():

    part = types.Part.from_bytes(data=b"\xff\xd8abc", mime_type="image/jpeg")

    msgs = build_messages([part, "o que tem aqui?"])

    assert len(msgs) == 1
    blocks = msgs[0]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[1] == {"type": "text", "text": "o que tem aqui?"}


def test_pdf_vira_documento():

    part = types.Part.from_bytes(data=b"%PDF-1.4", mime_type="application/pdf")

    assert build_messages([part])[0]["content"][0]["type"] == "document"


def test_midia_sem_suporte_levanta():

    part = types.Part.from_bytes(data=b"x", mime_type="audio/ogg")

    with pytest.raises(ClaudeUnsupported):

        build_messages([part])


def test_system_instruction_e_busca_web():

    config = types.GenerateContentConfig(
        system_instruction="Você é o coach.",
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    req = build_request("gemini-3.6-flash", "busca", config)

    assert req["system"] == "Você é o coach."
    assert req["tools"][0]["type"] == "web_search_20260209"


def test_schema_vai_no_prompt_de_sistema():

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={"headline": types.Schema(type=types.Type.STRING)},
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=schema,
    )

    req = build_request("gemini-3.6-flash", "x", config)

    assert "headline" in req["system"]


# ---- resposta ------------------------------------------------------------


def _message(content, stop="end_turn", usage=None):

    return SimpleNamespace(
        content=content,
        stop_reason=stop,
        stop_details=None,
        model="claude-sonnet-5-5",
        usage=usage or SimpleNamespace(
            input_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=900,
            output_tokens=50,
        ),
    )


def test_uso_no_formato_do_medidor():

    shim = usage_shim(_message([]))

    assert shim.prompt_token_count == 1000
    assert shim.candidates_token_count == 50


def test_fontes_da_busca_no_formato_gemini():

    msg = _message([
        SimpleNamespace(
            type="web_search_tool_result",
            content=[SimpleNamespace(url="https://x.com/p", title="Prova X")],
        ),
        SimpleNamespace(type="text", text="achei"),
    ])

    shim = grounding_shim(msg)

    chunk = shim.candidates[0].grounding_metadata.grounding_chunks[0]

    assert (chunk.web.uri, chunk.web.title) == ("https://x.com/p", "Prova X")
    assert shim.text == "achei"


def test_generate_continua_turno_pausado_e_junta_texto():

    first = _message([SimpleNamespace(type="text", text="parte 1 ")], stop="pause_turn")
    second = _message([SimpleNamespace(type="text", text="fim")])

    call = AsyncMock(side_effect=[first, second])

    with patch.object(adapter, "_call", call):

        text, model, _ = asyncio.run(
            adapter.generate("gemini-3.6-flash", "x", types.GenerateContentConfig())
        )

    assert text == "fim"
    assert call.await_count == 2
    assert model == "claude-sonnet-5-5"


def test_recusa_levanta():

    call = AsyncMock(return_value=_message([], stop="refusal"))

    with patch.object(adapter, "_call", call):

        with pytest.raises(adapter.ClaudeRefusal):

            asyncio.run(
                adapter.generate("gemini-3.6-flash", "x", types.GenerateContentConfig())
            )


# ---- integração com o cliente do Gemini ----------------------------------


def _run_client(**kwargs):

    return asyncio.run(
        gemini_client.generate_text(
            model="gemini-3.6-flash",
            contents="prompt",
            config=types.GenerateContentConfig(),
            **kwargs,
        )
    )


def _gemini_mock(text="do gemini"):

    mock = MagicMock()

    mock.aio.models.generate_content = AsyncMock(return_value=SimpleNamespace(text=text))

    return mock


def test_provider_claude_responde_sem_chamar_gemini():

    gemini = _gemini_mock()

    with patch(f"{GEMINI}.get_settings", return_value=_settings()), \
         patch(f"{GEMINI}._client", return_value=gemini), \
         patch.object(adapter, "generate", AsyncMock(return_value=("do claude", "claude-sonnet-5-5", None))):

        assert _run_client() == "do claude"

    gemini.aio.models.generate_content.assert_not_awaited()


def test_claude_falhando_cai_no_gemini():

    gemini = _gemini_mock()

    with patch(f"{GEMINI}.get_settings", return_value=_settings()), \
         patch(f"{GEMINI}._client", return_value=gemini), \
         patch.object(adapter, "generate", AsyncMock(side_effect=RuntimeError("fora do ar"))):

        assert _run_client() == "do gemini"


def test_claude_vazio_com_require_text_cai_no_gemini():

    gemini = _gemini_mock()

    with patch(f"{GEMINI}.get_settings", return_value=_settings()), \
         patch(f"{GEMINI}._client", return_value=gemini), \
         patch.object(adapter, "generate", AsyncMock(return_value=("  ", "claude-sonnet-5-5", None))):

        assert _run_client(require_text=True) == "do gemini"


def test_credito_do_claude_esgotado_avisa_e_cai_no_gemini():

    gemini = _gemini_mock()

    alert = AsyncMock()

    exc = RuntimeError("Your credit balance is too low to access the Anthropic API")

    with patch(f"{GEMINI}.get_settings", return_value=_settings()), \
         patch(f"{GEMINI}._client", return_value=gemini), \
         patch(f"{GEMINI}._alert_billing", alert), \
         patch.object(adapter, "generate", AsyncMock(side_effect=exc)):

        assert _run_client() == "do gemini"

    alert.assert_awaited_once()


def test_provider_gemini_nao_toca_no_claude():

    gemini = _gemini_mock()

    claude = AsyncMock()

    with patch(f"{GEMINI}.get_settings", return_value=_settings(ai_provider="gemini")), \
         patch(f"{GEMINI}._client", return_value=gemini), \
         patch.object(adapter, "generate", claude):

        assert _run_client() == "do gemini"

    claude.assert_not_awaited()
