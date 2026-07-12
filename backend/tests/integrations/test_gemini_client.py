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
