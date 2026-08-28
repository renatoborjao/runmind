from types import SimpleNamespace
from unittest.mock import patch

from app.application.shoes.shoe_recommendation_service import (
    ShoeRecommendationService,
)
from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule
from app.infrastructure.persistence.shoe_repository import ShoeRepository

MOD = "app.application.shoes.shoe_recommendation_service"


def _session(workout_type, day="Monday"):

    return SimpleNamespace(workout_type=workout_type, day=day)


def _rec(book, session):

    return ShoeRecommendationService.recommend(book, session)


def test_rule_drives_recommendation():

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", category="dia a dia",
                 is_default=True),
            Shoe(id="vapor", name="Vaporfly", category="prova"),
        ],
        rules=[ShoeRule(match="tiro", shoe_id="vapor")],
    )

    shoe, reason = _rec(book, _session("Tiros"))

    assert shoe.id == "vapor"
    assert "tiro" in reason


def test_quality_picks_prova_bucket():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, _ = _rec(book, _session("Fartlek"))

    assert shoe.id == "vapor"


def test_easy_run_uses_daily():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = _rec(book, _session("Rodagem leve"))

    assert shoe.id == "boston"
    assert "dia a dia" in reason


def test_long_run_stays_on_daily_even_progressive():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = _rec(book, _session("Longão Progressivo"))

    assert shoe.id == "boston"
    assert "longão" in reason.lower()


def test_rotation_varies_daily_shoes_across_days():
    """Com vários pares do dia a dia, dias diferentes pegam pares diferentes."""

    book = ShoeBook(shoes=[
        Shoe(id="a", name="A", category="dia a dia"),
        Shoe(id="b", name="B", category="dia a dia"),
    ])

    mon = _rec(book, _session("Rodagem", day="Monday"))[0]     # idx 0
    tue = _rec(book, _session("Rodagem", day="Tuesday"))[0]    # idx 1

    assert mon.id != tue.id
    assert "revezando" in _rec(book, _session("Rodagem"))[1]


def test_rotation_favors_freshest_on_first_index():

    book = ShoeBook(shoes=[
        Shoe(id="rodado", name="Rodado", category="dia a dia",
             initial_km=400.0),
        Shoe(id="novo", name="Novo", category="dia a dia", initial_km=20.0),
    ])

    # Monday -> idx 0 sobre a lista ordenada do mais NOVO pro mais rodado
    shoe, _ = _rec(book, _session("Rodagem", day="Monday"))

    assert shoe.id == "novo"


def test_rule_forced_worn_shoe_swaps_to_fresher():
    """Regra aponta um par GASTO -> troca pelo mais novo do mesmo balde."""

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", category="dia a dia",
                 initial_km=720.0, alert_threshold_km=700.0),
            Shoe(id="novo", name="Novo", category="dia a dia",
                 initial_km=50.0),
        ],
        rules=[ShoeRule(match="rodagem", shoe_id="boston")],
    )

    shoe, reason = _rec(book, _session("Rodagem"))

    assert shoe.id == "novo"
    assert "poupar" in reason and "Boston" in reason


def test_assignment_overrides_recommendation_for_that_date():
    """'quero o Red Hare no domingo' sobrepõe a recomendação SÓ naquela data."""

    book = ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", category="dia a dia",
                 is_default=True),
            Shoe(id="red", name="Red Hare", category="dia a dia"),
        ],
        assignments={"2026-08-30": "red"},
    )

    session = _session("Longão Progressivo", day="Sunday")

    # com a data fixada -> o par escolhido pelo atleta
    shoe, reason = ShoeRecommendationService.recommend(
        book, session, "2026-08-30"
    )
    assert shoe.id == "red"
    assert "pediu" in reason

    # OUTRA data (sem assignment) -> recomendação normal, sem o "você pediu"
    _, other_reason = ShoeRecommendationService.recommend(
        book, session, "2026-09-06"
    )
    assert "pediu" not in other_reason


def test_retired_assigned_shoe_is_ignored():

    book = ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", category="dia a dia",
                 is_default=True),
            Shoe(id="red", name="Red Hare", category="dia a dia", retired=True),
        ],
        assignments={"2026-08-30": "red"},
    )

    shoe, _ = ShoeRecommendationService.recommend(
        book, _session("Longão", day="Sunday"), "2026-08-30"
    )

    assert shoe.id == "vomero"  # ignora o aposentado, recomenda normal


def test_no_shoes_returns_none():

    assert _rec(ShoeBook(), _session("x")) is None


def test_single_shoe_is_always_the_pick():

    book = ShoeBook(shoes=[Shoe(id="one", name="Único")])

    shoe, _ = _rec(book, _session("Tiros"))

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
             category="dia a dia", is_default=True),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        line = ShoeRecommendationService.line("renato", _session("Rodagem leve"))

    assert line.startswith("👟 Sugestão de tênis: Boston")
