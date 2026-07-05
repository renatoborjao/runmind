import asyncio
from unittest.mock import AsyncMock, patch

from app.application.external_plan.external_plan_extraction_engine import (
    ExternalPlanExtractionEngine,
)

MODULE = (
    "app.application.external_plan.external_plan_extraction_engine"
)


def _extract(response_text: str | None):

    mock_generate = AsyncMock(return_value=response_text or "")

    with patch(f"{MODULE}.generate_text", new=mock_generate):

        sessions = asyncio.run(
            ExternalPlanExtractionEngine.extract(
                b"fake-image-bytes",
                "image/jpeg",
            )
        )

        return sessions, mock_generate


def test_extract_parses_sessions():

    sessions, mock_generate = _extract(
        '{"sessions": [{"day": "Tuesday", "workout_type": "Rodagem",'
        ' "distance_km": 6.0}]}'
    )

    assert sessions == [
        {"day": "Tuesday", "workout_type": "Rodagem",
         "distance_km": 6.0},
    ]

    _, kwargs = mock_generate.call_args
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
