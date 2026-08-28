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


def test_classify_super_trainer_normalized_to_daily():

    info = _classify(
        '{"category": "super trainer", "threshold_km": 600, "known": true}'
    )

    assert info["category"] == "dia a dia"


def test_classify_none_when_not_known():

    info = _classify(
        '{"category": "prova", "threshold_km": 420, "known": false}'
    )

    assert info is None


def test_classify_extracts_json_when_wrapped_in_prose():

    info = _classify(
        'Com base na busca: {"category": "dia a dia", "threshold_km": 700, '
        '"known": true} (fonte: reviews)'
    )

    assert info == {"category": "dia a dia", "threshold_km": 700.0}


def test_classify_none_when_generate_text_raises():

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(side_effect=RuntimeError("api down"))):

        assert asyncio.run(ShoeWebLookup.classify("qualquer")) is None


def test_classify_many_gathers_each_shoe():

    per_shoe = [
        '{"category": "prova", "threshold_km": 450, "known": true}',
        '{"category": "dia a dia", "threshold_km": 650, "known": true}',
    ]

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(side_effect=per_shoe)):

        out = asyncio.run(
            ShoeWebLookup.classify_many(["Vaporfly 3", "Boston 12"])
        )

    assert out["vaporfly 3"] == {"category": "prova", "threshold_km": 450.0}
    assert out["boston 12"] == {"category": "dia a dia", "threshold_km": 650.0}


def test_classify_many_omits_unknown():

    per_shoe = [
        '{"category": "prova", "threshold_km": 450, "known": true}',
        '{"category": null, "threshold_km": null, "known": false}',
    ]

    with patch(f"{MOD}.generate_text",
               new=AsyncMock(side_effect=per_shoe)):

        out = asyncio.run(ShoeWebLookup.classify_many(["Racer", "Desconhecido"]))

    assert "racer" in out and "desconhecido" not in out


def test_classify_many_empty_without_calling():

    web = AsyncMock()

    with patch(f"{MOD}.generate_text", new=web):

        assert asyncio.run(ShoeWebLookup.classify_many([])) == {}

    web.assert_not_awaited()
