import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from google.genai import errors as genai_errors

from app.infrastructure.integrations.gemini import client as gemini_client
from app.infrastructure.integrations.gemini.client import (
    EmptyGeminiResponse,
    generate_text,
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
