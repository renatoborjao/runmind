import asyncio
from unittest.mock import AsyncMock, patch

from app.application.shoes.shoe_web_lookup import ShoeWebLookup

MOD = "app.application.shoes.shoe_web_lookup"


def test_extract_snippets_pulls_result_text():

    html = (
        '<html><body>'
        '<a class="result__snippet" href="x">The Zoom Fly is a '
        '<b>carbon</b> plated racer</a>'
        '<a class="result__snippet">good for 400 km</a>'
        '</body></html>'
    )

    text = ShoeWebLookup._extract_snippets(html)

    assert "carbon" in text and "400 km" in text
    assert "<" not in text  # tags removidas


def _classify(search_text, gemini):

    with (
        patch(f"{MOD}.ShoeWebLookup._search",
              new=AsyncMock(return_value=search_text)),
        patch(f"{MOD}.generate_json", new=AsyncMock(return_value=gemini)),
    ):

        return asyncio.run(ShoeWebLookup.classify("Marca Modelo X"))


def test_classify_returns_category_and_threshold_when_known():

    info = _classify(
        "trechos reais sobre o tênis",
        {"category": "prova", "threshold_km": 420, "known": True},
    )

    assert info == {"category": "prova", "threshold_km": 420.0}


def test_classify_none_when_not_known():

    info = _classify(
        "trechos genéricos",
        {"category": "prova", "threshold_km": 420, "known": False},
    )

    assert info is None


def test_classify_none_when_search_empty():

    with patch(f"{MOD}.ShoeWebLookup._search",
               new=AsyncMock(return_value="")):

        assert asyncio.run(ShoeWebLookup.classify("qualquer")) is None


def test_classify_none_when_gemini_fails():

    info = _classify("trechos", None)

    assert info is None


def test_classify_drops_invalid_category_keeps_threshold():

    info = _classify(
        "trechos",
        {"category": "sei la", "threshold_km": 500, "known": True},
    )

    assert info == {"category": None, "threshold_km": 500.0}
