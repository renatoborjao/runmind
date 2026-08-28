import asyncio
from unittest.mock import AsyncMock, patch

from app.application.shoes.shoe_web_lookup import ShoeWebLookup

MOD = "app.application.shoes.shoe_web_lookup"


def _classify(gemini_text):

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(return_value=gemini_text)):

        return asyncio.run(ShoeWebLookup.classify("Marca Modelo X"))


def test_classify_returns_category_and_threshold_when_known():

    info = _classify(
        '{"category": "prova", "threshold_km": 420, "known": true}'
    )

    assert info == {"category": "prova", "threshold_km": 420.0}


def test_classify_parses_json_inside_markdown_fence():

    info = _classify(
        '```json\n{"category": "dia a dia", "threshold_km": 700, '
        '"known": true}\n```'
    )

    assert info == {"category": "dia a dia", "threshold_km": 700.0}


def test_classify_none_when_not_known():

    info = _classify(
        '{"category": "prova", "threshold_km": 420, "known": false}'
    )

    assert info is None


def test_classify_none_when_gemini_text_unparseable():

    assert _classify("desculpe, não achei nada útil") is None


def test_classify_none_when_generate_text_raises():

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(side_effect=RuntimeError("api down"))):

        assert asyncio.run(ShoeWebLookup.classify("qualquer")) is None


def test_classify_drops_invalid_category_keeps_threshold():

    info = _classify(
        '{"category": "sei la", "threshold_km": 500, "known": true}'
    )

    assert info == {"category": None, "threshold_km": 500.0}
