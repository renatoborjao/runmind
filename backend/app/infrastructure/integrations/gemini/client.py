import asyncio
import json
import re
from functools import lru_cache

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import get_settings

# Falha passageira do Gemini (rate limit do nível gratuito, indisponibilidade,
# timeout de rede) NÃO pode virar "me embananei" na cara do atleta na primeira
# tentativa: tenta de novo com backoff antes de desistir.
MAX_ATTEMPTS = 3

BASE_DELAY_SECONDS = 0.6

# Status HTTP que melhoram com retry: rate limit e indisponibilidade do
# servidor. 400/401/403 (pedido inválido, credencial, cota diária esgotada)
# não adiantam repetir — sobem direto pro fallback do chamador.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EmptyGeminiResponse(RuntimeError):
    """Gemini respondeu sem texto (bloqueio de safety, finish_reason
    inesperado). Para o chat vale tratar como falha e reenviar, em vez de
    mandar uma mensagem em branco pro atleta."""


@lru_cache
def _client() -> genai.Client:
    # Client é reaproveitado entre chamadas (antes um novo era criado por
    # mensagem); a chave vem do settings cacheado.
    return genai.Client(api_key=get_settings().google_api_key)


def _is_retryable(exc: Exception) -> bool:

    if isinstance(exc, EmptyGeminiResponse):

        return True

    # timeouts e erros de conexão/transporte do httpx
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):

        return True

    # APIError da lib do Gemini traz .code (status HTTP)
    code = getattr(exc, "code", None)

    return isinstance(code, int) and code in RETRYABLE_STATUS


async def generate_text(
    model: str,
    contents,
    config: types.GenerateContentConfig,
    *,
    require_text: bool = False,
) -> str:
    """Chama o Gemini com retry+backoff em falhas transitórias e devolve o
    texto da resposta.

    require_text=True (chat com o atleta): texto vazio vira falha e é
    reenviado; se persistir, levanta EmptyGeminiResponse para o chamador
    cair no fallback — nunca envia mensagem em branco.
    """

    last_exc: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):

        try:

            response = await _client().aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            text = response.text or ""

            if require_text and not text.strip():

                raise EmptyGeminiResponse()

            return text

        except Exception as exc:  # noqa: BLE001 — decide retry vs. propaga

            last_exc = exc

            is_last = attempt == MAX_ATTEMPTS - 1

            if is_last or not _is_retryable(exc):

                raise

            print(
                f"Gemini falhou (tentativa {attempt + 1}/{MAX_ATTEMPTS}, "
                f"{type(exc).__name__}): retry em backoff"
            )

            await asyncio.sleep(BASE_DELAY_SECONDS * (2 ** attempt))

    # inalcançável (o loop sempre retorna ou levanta), mas mantém o type-checker
    raise last_exc  # type: ignore[misc]


def repair_json(raw: str) -> str:
    """Conserta as escorregadas comuns do modelo antes do json.loads: tira
    cercas de markdown (```json ... ```) e recorta do primeiro { ou [ até o
    último } ou ] (ignora texto solto em volta). Não garante validade — só
    aumenta a chance de o json.loads passar."""

    text = (raw or "").strip()

    if text.startswith("```"):

        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)

        text = re.sub(r"\s*```$", "", text).strip()

    opens = [i for i in (text.find("{"), text.find("[")) if i != -1]

    start = min(opens) if opens else -1

    end = max(text.rfind("}"), text.rfind("]"))

    if start != -1 and end > start:

        text = text[start:end + 1]

    return text.strip()


async def generate_json(
    model: str,
    contents,
    config: types.GenerateContentConfig,
    *,
    parse,
    attempts: int = 3,
):
    """Gera JSON estruturado com blindagem em CAMADAS, pra a análise/plano
    nunca degradarem à toa:

    1) generate_text já tenta de novo em falha de API (429/5xx/timeout);
    2) aqui, se o JSON vier torto/incompleto (o modelo às vezes escorrega
       mesmo no modo JSON), RE-GERA e re-parseia até `attempts` vezes;
    3) `parse(raw)` deve reparar (repair_json) + validar e devolver None
       quando não dá — o chamador então cai no fallback determinístico.

    Nunca levanta por JSON ruim: devolve o objeto parseado ou None. Falha de
    API (após os retries internos) propaga pro try/except do chamador."""

    for attempt in range(attempts):

        raw = await generate_text(
            model=model,
            contents=contents,
            config=config,
            require_text=True,
        )

        result = parse(raw)

        if result is not None:

            return result

        print(
            f"Gemini JSON inválido (tentativa {attempt + 1}/{attempts}): "
            "re-gerando"
        )

    return None


# reexport pra quem precisa montar Part/config sem importar o SDK direto
__all__ = [
    "generate_text",
    "generate_json",
    "repair_json",
    "EmptyGeminiResponse",
    "genai_errors",
]
