"""Claude (API da Anthropic) atrás da MESMA interface do cliente do Gemini.

Os ~30 pontos do app montam `types.GenerateContentConfig` do Gemini e chamam
`gemini/client.generate_text`. Com `AI_PROVIDER=claude`, o cliente do Gemini
passa a chamada pra cá: este módulo TRADUZ conteúdo + config do Gemini pra
Messages API do Claude e devolve só o texto — os chamadores não mudam, e voltar
pro Gemini é uma linha no .env.

Mapeamento de modelo (por família, configurável no settings):
  Pro (plano)          -> claude_plan_model    (Opus 5.5)
  flash-lite (extração)-> claude_extract_model (Haiku 5.5)
  flash (chat/coach)   -> claude_chat_model    (Sonnet 5.5)

O que NÃO vem pra cá: a voz do coach (TTS do Gemini, o Claude não gera áudio).
Conteúdo que o Claude não aceita (áudio, imagem HEIC...) levanta
ClaudeUnsupported e o cliente cai no Gemini."""

import base64
import json
from functools import lru_cache
from types import SimpleNamespace

from app.core.config import get_settings

# folga de tokens pro raciocínio do Claude (o thinking conta DENTRO do
# max_tokens e não dá pra desligar no Opus/Sonnet 5.5). É teto: só cobra o
# que gerar. Piso de 16k pra resposta nunca sair cortada no meio.
MIN_MAX_TOKENS = 16_000

MAX_MAX_TOKENS = 64_000

THINKING_HEADROOM = 8_000

# web_search do Claude: buscas por chamada (cada uma custa ~US$ 0,01)
WEB_SEARCH_MAX_USES = 5

# rodadas de continuação quando a busca na web pausa o turno (pause_turn)
MAX_PAUSE_RESUMES = 3

# imagens que a API aceita; o resto (HEIC...) vai pro Gemini
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# recusa de segurança: o servidor tenta outro modelo sozinho (Opus/Sonnet)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_JSON_ONLY = (
    "Responda SOMENTE com JSON válido, sem texto antes ou depois e sem "
    "cercas de markdown."
)


class ClaudeUnsupported(RuntimeError):
    """Pedido que o Claude não atende (conteúdo/config sem tradução)."""


class ClaudeRefusal(RuntimeError):
    """Claude recusou por segurança (stop_reason=refusal)."""


@lru_cache
def _client():

    import anthropic

    settings = get_settings()

    # o SDK já repete 429/5xx/529 com backoff; o cliente do Gemini cuida do
    # resto (fallback pro Gemini se o Claude não responder)
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key or None,
        max_retries=3,
        timeout=600.0,
    )


def claude_model_for(gemini_model: str) -> tuple[str, str]:
    """(modelo Claude, papel) a partir do modelo Gemini que o chamador pediu."""

    settings = get_settings()

    name = (gemini_model or "").lower()

    if "pro" in name or name == (settings.plan_model or "").lower():

        return settings.claude_plan_model, "plan"

    if "lite" in name:

        return settings.claude_extract_model, "extract"

    return settings.claude_chat_model, "chat"


def effort_for(role: str, config) -> str:
    """Profundidade do raciocínio. Plano = settings (alto); extração = baixo;
    chat/coach segue o thinking_budget que o chamador pedia ao Gemini
    (0-512 = baixo, mais que isso = médio)."""

    settings = get_settings()

    if role == "plan":

        return settings.claude_plan_effort

    if role == "extract":

        return "low"

    thinking = getattr(config, "thinking_config", None)

    budget = getattr(thinking, "thinking_budget", None) if thinking else None

    if budget is not None and budget > 512:

        return "medium"

    return "low"


def max_tokens_for(config) -> int:

    out = getattr(config, "max_output_tokens", None) or 0

    return max(MIN_MAX_TOKENS, min(MAX_MAX_TOKENS, out + THINKING_HEADROOM))


def _system_text(config) -> str:

    system = getattr(config, "system_instruction", None)

    if system is None:

        return ""

    if isinstance(system, str):

        return system

    if isinstance(system, (list, tuple)):

        return "\n\n".join(_plain_text(item) for item in system)

    return _plain_text(system)


def _plain_text(item) -> str:

    if isinstance(item, str):

        return item

    if isinstance(item, dict):

        if "text" in item:

            return str(item["text"])

        return "\n".join(_plain_text(p) for p in item.get("parts", []))

    text = getattr(item, "text", None)

    if text:

        return text

    parts = getattr(item, "parts", None)

    if parts:

        return "\n".join(_plain_text(p) for p in parts)

    return str(item)


def _part_block(part) -> dict:
    """Uma parte do Gemini (texto, dict ou types.Part) -> bloco do Claude."""

    if isinstance(part, str):

        return {"type": "text", "text": part}

    if isinstance(part, dict):

        if "text" in part:

            return {"type": "text", "text": str(part["text"])}

        raise ClaudeUnsupported(f"parte sem tradução: {list(part)}")

    inline = getattr(part, "inline_data", None)

    if inline is not None and getattr(inline, "data", None) is not None:

        mime = (getattr(inline, "mime_type", None) or "").lower()

        data = base64.standard_b64encode(inline.data).decode("ascii")

        if mime in _IMAGE_TYPES:

            return {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": data},
            }

        if mime == "application/pdf":

            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": data,
                },
            }

        raise ClaudeUnsupported(f"tipo de mídia sem suporte no Claude: {mime}")

    text = getattr(part, "text", None)

    if text is not None:

        return {"type": "text", "text": text}

    raise ClaudeUnsupported(f"parte sem tradução: {type(part).__name__}")


def _turn(item) -> tuple[str, list] | None:
    """(papel, blocos) quando o item é um TURNO (dict/Content com role)."""

    role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)

    if role is None:

        return None

    parts = item.get("parts", []) if isinstance(item, dict) else (item.parts or [])

    claude_role = "assistant" if role == "model" else "user"

    return claude_role, [_part_block(p) for p in parts]


def build_messages(contents) -> list[dict]:
    """Conteúdo do Gemini -> lista de mensagens do Claude.

    Aceita: string; lista de partes (texto/imagem) = UMA mensagem do atleta;
    lista de turnos {"role", "parts"} = conversa. Turnos seguidos do mesmo
    papel são fundidos; a conversa sempre começa e termina no usuário."""

    if isinstance(contents, str):

        return [{"role": "user", "content": [{"type": "text", "text": contents}]}]

    items = list(contents) if isinstance(contents, (list, tuple)) else [contents]

    turns: list[tuple[str, list]] = []

    loose: list = []

    for item in items:

        turn = _turn(item)

        if turn is None:

            loose.append(_part_block(item))

        else:

            turns.append(turn)

    if loose:

        turns.append(("user", loose))

    messages: list[dict] = []

    for role, blocks in turns:

        blocks = [b for b in blocks if b.get("type") != "text" or b["text"].strip()]

        if not blocks:

            continue

        if messages and messages[-1]["role"] == role:

            messages[-1]["content"].extend(blocks)

        else:

            messages.append({"role": role, "content": list(blocks)})

    if not messages or messages[0]["role"] != "user":

        messages.insert(
            0, {"role": "user", "content": [{"type": "text", "text": "(início)"}]}
        )

    if messages[-1]["role"] != "user":

        messages.append(
            {"role": "user", "content": [{"type": "text", "text": "(continue)"}]}
        )

    return messages


def _wants_web_search(config) -> bool:

    for tool in getattr(config, "tools", None) or []:

        if getattr(tool, "google_search", None) is not None:

            return True

        raise ClaudeUnsupported("ferramenta do Gemini sem tradução")

    return False


def build_request(model: str, contents, config) -> dict:
    """Pedido completo da Messages API (sem o client), testável sem rede."""

    claude_model, role = claude_model_for(model)

    system = _system_text(config)

    json_mode = (getattr(config, "response_mime_type", None) or "") == "application/json"

    if json_mode:

        schema = getattr(config, "response_schema", None)

        extra = _JSON_ONLY

        if schema is not None:

            dumped = schema.model_dump(exclude_none=True, mode="json")

            extra += "\nFormato (schema): " + json.dumps(dumped, ensure_ascii=False)

        system = f"{system}\n\n{extra}" if system else extra

    request: dict = {
        "model": claude_model,
        "max_tokens": max_tokens_for(config),
        "messages": build_messages(contents),
        "output_config": {"effort": effort_for(role, config)},
        # cache automático do maior prefixo (prompt de sistema do coach é
        # grande e se repete): leitura do cache custa ~10%
        "cache_control": {"type": "ephemeral"},
    }

    if system:

        request["system"] = system

    if _wants_web_search(config):

        request["tools"] = [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": WEB_SEARCH_MAX_USES,
            }
        ]

    # Haiku não tem fallback de recusa no servidor
    if "haiku" not in claude_model:

        request["betas"] = [_FALLBACK_BETA]

        request["fallbacks"] = "default"

    return request


def response_text(message) -> str:

    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )


def usage_shim(message):
    """Uso no formato que o TokenMeter lê (campos do Gemini). Cache conta como
    entrada (a estimativa de custo fica um pouco acima do real)."""

    usage = getattr(message, "usage", None)

    if usage is None:

        return None

    tokens_in = (
        (getattr(usage, "input_tokens", 0) or 0)
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )

    tokens_out = getattr(usage, "output_tokens", 0) or 0

    return SimpleNamespace(
        prompt_token_count=tokens_in,
        candidates_token_count=tokens_out,
        thoughts_token_count=0,
        total_token_count=tokens_in + tokens_out,
    )


def grounding_shim(message):
    """Fontes da busca na web no formato que o race_intel lê do Gemini
    (response.candidates[0].grounding_metadata.grounding_chunks[].web)."""

    chunks = []

    for block in message.content:

        if getattr(block, "type", "") != "web_search_tool_result":

            continue

        results = getattr(block, "content", None)

        if not isinstance(results, list):

            continue

        for result in results:

            url = getattr(result, "url", None)

            if url:

                chunks.append(
                    SimpleNamespace(
                        web=SimpleNamespace(uri=url, title=getattr(result, "title", "") or "")
                    )
                )

    meta = SimpleNamespace(grounding_chunks=chunks)

    return SimpleNamespace(
        text=response_text(message),
        candidates=[SimpleNamespace(grounding_metadata=meta)],
        usage_metadata=usage_shim(message),
        claude_message=message,
    )


async def _call(request: dict):

    client = _client()

    params = dict(request)

    betas = params.pop("betas", None)

    if betas:

        async with client.beta.messages.stream(betas=betas, **params) as stream:

            return await stream.get_final_message()

    async with client.messages.stream(**params) as stream:

        return await stream.get_final_message()


async def generate(model: str, contents, config, capture: list | None = None):
    """Chama o Claude e devolve (texto, modelo Claude usado, uso no formato
    Gemini). Levanta ClaudeUnsupported/ClaudeRefusal ou o erro do SDK."""

    request = build_request(model, contents, config)

    message = await _call(request)

    # busca na web longa pode pausar o turno: devolve e o servidor continua
    for _ in range(MAX_PAUSE_RESUMES):

        if message.stop_reason != "pause_turn":

            break

        request["messages"] = [
            *request["messages"],
            {"role": "assistant", "content": message.content},
        ]

        message = await _call(request)

    if message.stop_reason == "refusal":

        raise ClaudeRefusal(
            f"Claude recusou ({getattr(message.stop_details, 'category', None)})"
        )

    if capture is not None:

        capture.append(grounding_shim(message))

    return response_text(message), getattr(message, "model", request["model"]), usage_shim(message)
