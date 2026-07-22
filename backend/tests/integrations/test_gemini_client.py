import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from google.genai import errors as genai_errors

from app.infrastructure.integrations.gemini import client as gemini_client
from app.infrastructure.integrations.gemini.client import (
    EmptyGeminiResponse,
    generate_json,
    generate_text,
    repair_json,
)

MODULE = "app.infrastructure.integrations.gemini.client"


def _mock_client(generate_content: AsyncMock) -> MagicMock:

    mock = MagicMock()

    mock.aio.models.generate_content = generate_content

    return mock


def _run(**kwargs):

    return asyncio.run(
        generate_text(
            model="modelo",
            contents="prompt",
            config=SimpleNamespace(),
            **kwargs,
        )
    )


def _server_error() -> genai_errors.ServerError:

    return genai_errors.ServerError(503, {"error": {"message": "indisponível"}})


def test_returns_text_on_first_success():

    generate_content = AsyncMock(
        return_value=SimpleNamespace(text="olá"),
    )

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        assert _run() == "olá"

    assert generate_content.await_count == 1


def test_retries_transient_error_then_succeeds():

    generate_content = AsyncMock(
        side_effect=[
            _server_error(),
            SimpleNamespace(text="deu certo"),
        ],
    )

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()):

            assert _run() == "deu certo"

    assert generate_content.await_count == 2


def test_gives_up_after_max_attempts():

    generate_content = AsyncMock(side_effect=_server_error())

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()):

            with pytest.raises(genai_errors.ServerError):

                _run()

    assert generate_content.await_count == gemini_client.MAX_ATTEMPTS


def _rate_limit() -> genai_errors.ClientError:

    return genai_errors.ClientError(429, {"error": {"message": "rate limit"}})


def test_cascades_to_fallback_model_without_waiting():

    # primário (flash) estourou a cota: tenta o fallback (flash-lite) na
    # MESMA rodada, sem esperar, e responde por ele
    generate_content = AsyncMock(
        side_effect=[_rate_limit(), SimpleNamespace(text="via lite")],
    )

    sleep = AsyncMock()

    with (
        patch(f"{MODULE}._client", return_value=_mock_client(generate_content)),
        patch(f"{MODULE}.asyncio.sleep", new=sleep),
    ):

        result = asyncio.run(
            generate_text(
                model="gemini-3.5-flash",
                contents="prompt",
                config=SimpleNamespace(),
            )
        )

    assert result == "via lite"
    assert generate_content.await_count == 2
    # trocar de modelo é imediato — não gastou backoff
    sleep.assert_not_awaited()
    # o 2º disparo foi no fallback certo
    assert (
        generate_content.await_args_list[1].kwargs["model"]
        == "gemini-3.5-flash-lite"
    )


def test_all_models_down_raises_after_full_cascade():

    # 429 em todos os modelos, em todas as rodadas: só então desiste
    generate_content = AsyncMock(side_effect=_rate_limit())

    with (
        patch(f"{MODULE}._client", return_value=_mock_client(generate_content)),
        patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()),
    ):

        with pytest.raises(genai_errors.ClientError):

            asyncio.run(
                generate_text(
                    model="gemini-3.5-flash",
                    contents="prompt",
                    config=SimpleNamespace(),
                )
            )

    # flash tem 2 fallbacks -> 3 modelos x MAX_ATTEMPTS rodadas
    assert generate_content.await_count == 3 * gemini_client.MAX_ATTEMPTS


def test_config_role_models_have_fallback_chains():

    # os três papéis do config precisam de cascata no client — sem entrada,
    # o modelo roda sem fallback e uma indisponibilidade vira falha direta
    from app.core.config import Settings

    settings = Settings(telegram_bot_token="x", google_api_key="x")

    for role_model in (
        settings.gemini_chat_model,
        settings.gemini_extract_model,
        settings.gemini_coach_model,
    ):

        assert role_model in gemini_client._FALLBACK_MODELS, role_model

        # e a cadeia nunca aponta pra si mesma
        assert role_model not in gemini_client._FALLBACK_MODELS[role_model]


def test_suggested_retry_delay_parsed_and_backoff_capped():

    exc = Exception("RESOURCE_EXHAUSTED ... 'retryDelay': '7s' ...")

    assert gemini_client._suggested_retry_delay(exc) == 7.0

    # mesmo com a API pedindo 600s, o backoff inline tem teto
    huge = Exception("retryDelay: '600s'")

    assert (
        gemini_client._backoff_delay(huge, 0)
        <= gemini_client.MAX_BACKOFF_SECONDS
    )


def test_timeout_is_retryable():

    generate_content = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            SimpleNamespace(text="ok"),
        ],
    )

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()):

            assert _run() == "ok"


def test_client_error_400_is_not_retried():

    # pedido inválido / credencial não melhora com retry: sobe na hora
    bad_request = genai_errors.ClientError(400, {"error": {"message": "ruim"}})

    generate_content = AsyncMock(side_effect=bad_request)

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()):

            with pytest.raises(genai_errors.ClientError):

                _run()

    assert generate_content.await_count == 1


def test_require_text_retries_on_empty_then_raises():

    generate_content = AsyncMock(
        return_value=SimpleNamespace(text=""),
    )

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()):

            with pytest.raises(EmptyGeminiResponse):

                _run(require_text=True)

    assert generate_content.await_count == gemini_client.MAX_ATTEMPTS


def test_thinking_budget_zero_is_raised_to_floor():

    # os modelos 3.x rejeitam thinking_budget=0 (400); o cliente eleva pro
    # piso válido ANTES de disparar, pra o request não virar inválido
    thinking = SimpleNamespace(thinking_budget=0)

    config = SimpleNamespace(thinking_config=thinking, max_output_tokens=400)

    generate_content = AsyncMock(return_value=SimpleNamespace(text="ok"))

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        result = asyncio.run(
            generate_text(model="modelo", contents="p", config=config),
        )

    assert result == "ok"
    # 0 virou o mínimo válido (nunca chega 0 na API)
    assert thinking.thinking_budget == gemini_client.MINIMAL_THINKING_BUDGET


def test_thinking_budget_above_floor_is_left_untouched():

    # budget explícito dos chamadores pesados (plano/análise) não é mexido
    thinking = SimpleNamespace(thinking_budget=512)

    config = SimpleNamespace(thinking_config=thinking, max_output_tokens=6000)

    generate_content = AsyncMock(return_value=SimpleNamespace(text="ok"))

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        asyncio.run(
            generate_text(model="modelo", contents="p", config=config),
        )

    assert thinking.thinking_budget == 512


def test_thinking_headroom_added_to_max_output_tokens():

    # thinking é cobrado dentro do max_output_tokens e nao respeita o budget
    # como teto -> soma folga pro thinking nao truncar a saida do chamador
    thinking = SimpleNamespace(thinking_budget=1)

    config = SimpleNamespace(thinking_config=thinking, max_output_tokens=400)

    generate_content = AsyncMock(return_value=SimpleNamespace(text="ok"))

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        asyncio.run(
            generate_text(model="modelo", contents="p", config=config),
        )

    assert (
        config.max_output_tokens
        == 400 + gemini_client.THINKING_HEADROOM
    )


def test_config_without_thinking_config_passes_intact():

    # config de JSON puro (sem thinking_config) nao mexe budget nem max
    config = SimpleNamespace(max_output_tokens=800)

    generate_content = AsyncMock(return_value=SimpleNamespace(text="ok"))

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        assert asyncio.run(
            generate_text(model="modelo", contents="p", config=config),
        ) == "ok"

    # sem thinking_config, nada de folga -> max_output_tokens intacto
    assert config.max_output_tokens == 800


def test_empty_text_allowed_when_not_required():

    generate_content = AsyncMock(
        return_value=SimpleNamespace(text=None),
    )

    with patch(f"{MODULE}._client", return_value=_mock_client(generate_content)):

        assert _run() == ""

    assert generate_content.await_count == 1


# ---------------- repair_json ----------------


def test_repair_strips_markdown_fences():

    assert repair_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert repair_json('```\n[1, 2]\n```') == '[1, 2]'


def test_repair_extracts_json_from_surrounding_text():

    assert repair_json('Claro! {"a": 1} pronto.') == '{"a": 1}'


def test_repair_passes_valid_json_through():

    assert repair_json('{"a": 1}') == '{"a": 1}'


# ---------------- generate_json (retry de parse) ----------------


def _json_parse(raw):

    import json

    try:

        data = json.loads(repair_json(raw))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None

    return data if isinstance(data, dict) else None


def _run_json(responses):

    mock = AsyncMock(side_effect=responses)

    with patch(f"{MODULE}.generate_text", new=mock):

        result = asyncio.run(
            generate_json(
                model="m", contents="c", config=SimpleNamespace(),
                parse=_json_parse, attempts=3,
            )
        )

    return result, mock


def test_generate_json_returns_on_first_valid():

    result, mock = _run_json(['{"ok": 1}'])

    assert result == {"ok": 1}
    assert mock.await_count == 1


def test_generate_json_retries_malformed_then_succeeds():

    # 1ª torta (JSON incompleto), 2ª válida -> re-gera e acerta
    result, mock = _run_json(['{"ok": ', '{"ok": 2}'])

    assert result == {"ok": 2}
    assert mock.await_count == 2


def test_generate_json_none_after_all_attempts_fail():

    result, mock = _run_json(["nope", "still bad", "ugh"])

    assert result is None
    assert mock.await_count == 3
