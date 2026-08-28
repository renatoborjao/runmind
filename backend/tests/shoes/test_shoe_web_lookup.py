import asyncio
from unittest.mock import AsyncMock, patch

from app.application.shoes.shoe_web_lookup import ShoeWebLookup

MOD = "app.application.shoes.shoe_web_lookup"


def _classify_many(names, gemini_text):

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(return_value=gemini_text)):

        return asyncio.run(ShoeWebLookup.classify_many(names))


def test_classifies_each_shoe_from_search():

    out = _classify_many(
        ["Vaporfly 3", "Boston 12"],
        '{"shoes": ['
        '{"name": "Vaporfly 3", "category": "prova", "threshold_km": 450},'
        '{"name": "Boston 12", "category": "dia a dia", "threshold_km": 650}'
        ']}',
    )

    assert out["vaporfly 3"] == {"category": "prova", "threshold_km": 450.0}
    assert out["boston 12"] == {"category": "dia a dia", "threshold_km": 650.0}


def test_super_trainer_normalized_to_daily():
    """'super trainer' cai no balde de rodagem (uso = volume)."""

    out = _classify_many(
        ["Red Hare 9 Ultra"],
        '{"shoes": [{"name": "Red Hare 9 Ultra", '
        '"category": "super trainer", "threshold_km": 600}]}',
    )

    assert out["red hare 9 ultra"]["category"] == "dia a dia"


def test_unknown_model_is_omitted():

    out = _classify_many(
        ["Modelo Inexistente"],
        '{"shoes": [{"name": "Modelo Inexistente", '
        '"category": null, "threshold_km": null}]}',
    )

    assert out == {}


def test_empty_names_returns_empty_without_calling():

    web = AsyncMock()

    with patch(f"{MOD}.generate_text", new=web):

        assert asyncio.run(ShoeWebLookup.classify_many([])) == {}

    web.assert_not_awaited()


def test_json_wrapped_in_prose_is_extracted():

    out = _classify_many(
        ["Clifton 9"],
        'Aqui: {"shoes": [{"name": "Clifton 9", "category": "dia a dia", '
        '"threshold_km": 800}]} (fonte: reviews)',
    )

    assert out["clifton 9"]["category"] == "dia a dia"


def test_generate_text_failure_returns_empty():

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(side_effect=RuntimeError("api down"))):

        assert asyncio.run(ShoeWebLookup.classify_many(["X"])) == {}
