import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.external_plan.external_plan_extraction_engine import (
    ExternalPlanExtractionEngine,
)

MODULE = (
    "app.application.external_plan.external_plan_extraction_engine"
)


def _extract(response_text: str | None):

    with patch(f"{MODULE}.genai.Client") as mock_client_cls:

        mock_client = mock_client_cls.return_value

        mock_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text=response_text),
        )

        sessions = asyncio.run(
            ExternalPlanExtractionEngine.extract(
                b"fake-image-bytes",
                "image/jpeg",
            )
        )

        return sessions, mock_client


def test_extract_parses_sessions():

    sessions, mock_client = _extract(
        '{"sessions": [{"day": "Tuesday", "workout_type": "Rodagem",'
        ' "distance_km": 6.0}]}'
    )

    assert sessions == [
        {"day": "Tuesday", "workout_type": "Rodagem",
         "distance_km": 6.0},
    ]

    _, kwargs = mock_client.aio.models.generate_content.call_args
    assert kwargs["config"].response_mime_type == "application/json"


def test_malformed_json_returns_empty_list():

    sessions, _ = _extract("isso não é json")

    assert sessions == []


def test_missing_sessions_key_returns_empty_list():

    sessions, _ = _extract('{"outra_coisa": 1}')

    assert sessions == []


def test_non_dict_items_are_filtered():

    sessions, _ = _extract(
        '{"sessions": [{"day": "Monday"}, "lixo", 42]}'
    )

    assert sessions == [{"day": "Monday"}]
