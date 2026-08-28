from types import SimpleNamespace
from unittest.mock import patch

from app.application.shoes.shoe_recommendation_service import (
    ShoeRecommendationService,
)
from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule
from app.infrastructure.persistence.shoe_repository import ShoeRepository

MOD = "app.application.shoes.shoe_recommendation_service"


def _session(workout_type):

    return SimpleNamespace(workout_type=workout_type)


def test_rule_drives_recommendation():

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", is_default=True),
            Shoe(id="vapor", name="Vaporfly"),
        ],
        rules=[ShoeRule(match="tiro", shoe_id="vapor")],
    )

    shoe, reason = ShoeRecommendationService.recommend(book, _session("Tiros"))

    assert shoe.id == "vapor"
    assert "tiro" in reason


def test_quality_picks_race_shoe_by_category_without_rule():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, _ = ShoeRecommendationService.recommend(book, _session("Fartlek"))

    assert shoe.id == "vapor"


def test_easy_run_uses_default():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = ShoeRecommendationService.recommend(
        book, _session("Rodagem leve")
    )

    assert shoe.id == "boston"
    assert "dia a dia" in reason


def test_wear_deviates_to_fresher_shoe():
    """Par indicado gasto + alternativo mais novo -> manda o novo pra poupar."""

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", is_default=True,
             initial_km=720.0, alert_threshold_km=700.0),
        Shoe(id="novo", name="Par Novo", initial_km=50.0),
    ])

    shoe, reason = ShoeRecommendationService.recommend(
        book, _session("Rodagem leve")
    )

    assert shoe.id == "novo"
    assert "poupar" in reason and "Boston" in reason


def test_long_run_stays_on_daily_shoe_even_progressive():
    """Longão é conforto — vai no par do dia a dia mesmo progressivo (nada de
    placa de carbono no longão)."""

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = ShoeRecommendationService.recommend(
        book, _session("Longão Progressivo")
    )

    assert shoe.id == "boston"
    assert "longão" in reason.lower()


def test_no_shoes_returns_none():

    assert ShoeRecommendationService.recommend(ShoeBook(), _session("x")) is None


def test_single_shoe_is_always_the_pick():

    book = ShoeBook(shoes=[Shoe(id="one", name="Único")])

    shoe, _ = ShoeRecommendationService.recommend(book, _session("Tiros"))

    assert shoe.id == "one"


def test_line_is_silent_without_shoes(tmp_path):

    repo = ShoeRepository()
    repo.storage = tmp_path

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        assert ShoeRecommendationService.line("renato", _session("Tiros")) == ""


def test_line_formats_suggestion(tmp_path):

    repo = ShoeRepository()
    repo.storage = tmp_path
    repo.save("renato", ShoeBook(shoes=[
        Shoe(id="boston", name="Adidas Boston", nickname="Boston",
             is_default=True),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        line = ShoeRecommendationService.line("renato", _session("Rodagem leve"))

    assert line.startswith("👟 Sugestão de tênis: Boston")
