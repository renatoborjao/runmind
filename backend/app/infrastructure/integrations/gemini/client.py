import asyncio
import json
import random
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

# teto do backoff INLINE: uma tarefa de background não deve ficar parada
# minutos esperando o rate limit resetar. Esperas longas (reset de RPM) são
# problema da camada de retry ADIADO do webhook, não daqui.
MAX_BACKOFF_SECONDS = 8.0

# Status HTTP que melhoram com retry: rate limit e indisponibilidade do
# servidor. 400/401/403 (pedido inválido, credencial, cota diária esgotada)
# não adiantam repetir — sobem direto pro fallback do chamador.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Piso de thinking_budget. Os aliases "-latest" do Gemini passaram a apontar
# (2026-07) pra modelos que REJEITAM thinking_budget=0 com 400
# INVALID_ARGUMENT — não dá mais pra desligar o thinking por completo. Vários
# chamadores pediam 0 ("o mínimo possível, sem raciocínio") e de um dia pro
# outro TODO request deles virou inválido (nenhuma mudança nossa; o Google
# moveu o alias). Aqui, no único ponto por onde toda chamada passa, qualquer
# budget abaixo do piso é elevado pro mínimo válido — mantém a intenção
# (custo/latência mínimos) sem o request quebrar. 400 não é retryável, então
# sem isso a falha ia direto pro "me embananei" na cara do atleta.
MINIMAL_THINKING_BUDGET = 1

# Folga pro thinking, SOMADA ao max_output_tokens que o chamador pediu.
# Nos modelos 3.x o thinking (a) é obrigatório e (b) NÃO respeita o
# thinking_budget como teto — mede-se ~700-1300 tokens de raciocínio mesmo
# com budget=1. E ele é cobrado DENTRO do max_output_tokens. Então quando o
# chamador dimensiona max_output_tokens só pro TEXTO que quer, o thinking
# come esse orçamento e a resposta sai cortada no meio (bug real do chat:
# "Amanhã, quarta-feira (22/"). Aqui damos espaço próprio pro thinking em
# cima do pedido — max_output_tokens volta a significar "tamanho da SAÍDA".
# É TETO (só cobra o que gera), então a folga não custa nada além dos tokens
# de thinking que de fato acontecerem. 2048 cobre o pico observado (~1300)
# com margem. Ver [[project_gemini_alias_thinking_bug]].
THINKING_HEADROOM = 2048

# CASCATA DE MODELOS: se o primário está com a cota estourada (429) ou
# sobrecarregado (503), a gente NÃO desiste — tenta outro modelo cuja cota é
# independente ANTES do fallback "me embananei". No nível gratuito cada
# modelo tem seu próprio balde de RPM/RPD, então trocar de modelo resgata a
# esmagadora maioria dos 429. flash-lite quase nunca satura; é a rede final.
# Ordem = qualidade decrescente a partir do primário.
# Chaveado pelas versões PINADas do config (não mais pelos aliases -latest,
# ver [[project_gemini_alias_thinking_bug]]). Cada modelo cai nos outros da
# família 3.x flash (cota independente); mantidos em sincronia com os três
# papéis de app/core/config.py — ao trocar um modelo lá, atualizar aqui.
_FALLBACK_MODELS = {
    "gemini-3.5-flash": [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ],
    "gemini-3.5-flash-lite": [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
    ],
    "gemini-3.1-flash-lite": [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
    ],
}


def _model_candidates(model: str) -> list[str]:
    """O modelo pedido seguido dos seus fallbacks (cota independente).
    Modelo desconhecido roda sem cascata (só ele)."""

    return [model, *_FALLBACK_MODELS.get(model, [])]


# retryDelay que a própria API sugere no corpo do 429 (RetryInfo). Honrar
# isso é mais preciso que o backoff cego.
_RETRY_DELAY_RE = re.compile(
    r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
)


def _suggested_retry_delay(exc: Exception) -> float:
    """Segundos que o Gemini pediu pra esperar (0 se não informou)."""

    match = _RETRY_DELAY_RE.search(str(exc))

    return float(match.group(1)) if match else 0.0


def _backoff_delay(exc: Exception | None, attempt: int) -> float:
    """Backoff exponencial, respeitando o retryDelay da API quando vier,
    com jitter (±25%) pra entregas concorrentes não ressincronizarem — e
    com teto pra não travar a tarefa de background."""

    base = BASE_DELAY_SECONDS * (2 ** attempt)

    suggested = _suggested_retry_delay(exc) if exc else 0.0

    # jitter (±25%) antes do teto, pra o cap ser um limite de verdade
    delay = max(base, suggested) * (0.75 + random.random() * 0.5)

    return min(delay, MAX_BACKOFF_SECONDS)


class EmptyGeminiResponse(RuntimeError):
    """Gemini respondeu sem texto (bloqueio de safety, finish_reason
    inesperado). Para o chat vale tratar como falha e reenviar, em vez de
    mandar uma mensagem em branco pro atleta."""


@lru_cache
def _client() -> genai.Client:
    # Client é reaproveitado entre chamadas (antes um novo era criado por
    # mensagem); a chave vem do settings cacheado.
    return genai.Client(api_key=get_settings().google_api_key)


def _normalize_thinking(config) -> None:
    """Ajusta o config de thinking pros modelos 3.x, in-place (os chamadores
    montam o config fresco a cada chamada; config sem thinking_config — ex.:
    JSON puro sem raciocínio — passa intacto):

    1) eleva thinking_budget=0 (rejeitado com 400) pro piso válido;
    2) soma THINKING_HEADROOM ao max_output_tokens, pra o thinking (cobrado
       dentro desse teto) não comer a saída e truncar a resposta."""

    thinking = getattr(config, "thinking_config", None)

    if thinking is None:

        return

    budget = getattr(thinking, "thinking_budget", None)

    if budget is not None and budget < MINIMAL_THINKING_BUDGET:

        thinking.thinking_budget = MINIMAL_THINKING_BUDGET

    max_out = getattr(config, "max_output_tokens", None)

    if max_out is not None:

        config.max_output_tokens = max_out + THINKING_HEADROOM


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

    _normalize_thinking(config)

    candidates = _model_candidates(model)

    last_exc: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):

        # em cada rodada, tenta o primário e, se ele estiver indisponível,
        # cada fallback SEM esperar (cota independente resgata na hora).
        for candidate in candidates:

            try:

                response = await _client().aio.models.generate_content(
                    model=candidate,
                    contents=contents,
                    config=config,
                )

                text = response.text or ""

                if require_text and not text.strip():

                    raise EmptyGeminiResponse()

                if candidate != model:

                    print(
                        f"Gemini respondeu no fallback '{candidate}' "
                        f"(primário '{model}' indisponível)"
                    )

                return text

            except Exception as exc:  # noqa: BLE001 — decide retry vs. propaga

                last_exc = exc

                # erro que não melhora com retry (400/401/403 — pedido
                # inválido, credencial) é igual em qualquer modelo: sobe já
                if not _is_retryable(exc):

                    raise

                # indisponível neste modelo: tenta o próximo candidato
                continue

        # todos os modelos falharam nesta rodada; só então espera e repete
        is_last = attempt == MAX_ATTEMPTS - 1

        if is_last:

            break

        delay = _backoff_delay(last_exc, attempt)

        print(
            f"Todos os modelos Gemini indisponíveis "
            f"(rodada {attempt + 1}/{MAX_ATTEMPTS}, "
            f"{type(last_exc).__name__}): backoff {delay:.1f}s"
        )

        await asyncio.sleep(delay)

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
