from app.application.shoes.shoe_attribution_resolver import (
    BY_ASSIGN,
    BY_DEFAULT,
    BY_GEAR,
    BY_RECOMMENDED,
    BY_RULE,
    ShoeAttributionResolver,
)
from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule


def _book():

    return ShoeBook(
        shoes=[
            Shoe(id="boston", name="Adidas Boston", is_default=True),
            Shoe(id="vapor", name="Nike Vaporfly", gear_id="g999"),
            Shoe(id="old", name="Velho", retired=True, gear_id="g000"),
        ],
        rules=[ShoeRule(match="tiro", shoe_id="vapor")],
    )


def test_gear_wins_over_everything():

    attr = ShoeAttributionResolver.resolve(_book(), "g999", ("Longão",))

    assert attr.shoe.id == "vapor"
    assert attr.how == BY_GEAR


def test_rule_matches_workout_label():

    attr = ShoeAttributionResolver.resolve(_book(), None, ("Tiros", "INTERVAL"))

    assert attr.shoe.id == "vapor"
    assert attr.how == BY_RULE


def test_default_when_no_gear_no_rule():

    attr = ShoeAttributionResolver.resolve(_book(), None, ("Rodagem leve",))

    assert attr.shoe.id == "boston"
    assert attr.how == BY_DEFAULT


def test_none_when_no_shoes():

    assert ShoeAttributionResolver.resolve(ShoeBook(), "g1", ("x",)) is None


def test_retired_shoe_never_attributed_even_by_gear():
    """Um par aposentado não recebe corrida nem casando o gear."""

    book = ShoeBook(shoes=[Shoe(id="old", name="Velho", retired=True,
                               gear_id="g000")])

    assert ShoeAttributionResolver.resolve(book, "g000", ("x",)) is None


def test_rule_pointing_to_missing_shoe_falls_through_to_default():

    book = ShoeBook(
        shoes=[Shoe(id="boston", name="Boston", is_default=True)],
        rules=[ShoeRule(match="tiro", shoe_id="ghost")],
    )

    attr = ShoeAttributionResolver.resolve(book, None, ("Tiros",))

    assert attr.shoe.id == "boston"
    assert attr.how == BY_DEFAULT


# ---- recomendação do coach dirige a atribuição (fim do "contou no padrão") --


def _reco_book():

    return ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", is_default=True),   # padrão
            Shoe(id="evo", name="Evo SL", category="versátil"),
            Shoe(id="red", name="Red Hare", category="dia a dia"),
        ],
        recommended={"2026-09-01": "evo"},
        assignments={"2026-09-02": "red"},
    )


def test_recommended_beats_default_for_the_date():
    """O bug do Renato: recomendou Evo SL, contava no Vomero. Agora conta no
    par recomendado pra AQUELA data."""

    attr = ShoeAttributionResolver.resolve(
        _reco_book(), None, ("Tempo",), session_date_iso="2026-09-01"
    )

    assert attr.shoe.id == "evo"
    assert attr.how == BY_RECOMMENDED


def test_athlete_assignment_beats_recommendation():

    attr = ShoeAttributionResolver.resolve(
        _reco_book(), None, ("Rodagem",), session_date_iso="2026-09-02"
    )

    assert attr.shoe.id == "red"
    assert attr.how == BY_ASSIGN


def test_gear_still_wins_over_recommendation():

    book = _reco_book()
    book.get("red").gear_id = "g1"

    attr = ShoeAttributionResolver.resolve(
        book, "g1", ("Tempo",), session_date_iso="2026-09-01"
    )

    assert attr.shoe.id == "red"
    assert attr.how == BY_GEAR


def test_falls_to_default_when_no_recommendation_for_date():

    attr = ShoeAttributionResolver.resolve(
        _reco_book(), None, ("Rodagem",), session_date_iso="2026-09-09"
    )

    assert attr.shoe.id == "vomero"
    assert attr.how == BY_DEFAULT


def test_recommendation_to_retired_shoe_falls_through():

    book = ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", is_default=True),
            Shoe(id="evo", name="Evo SL", retired=True),
        ],
        recommended={"2026-09-01": "evo"},
    )

    attr = ShoeAttributionResolver.resolve(
        book, None, ("Tempo",), session_date_iso="2026-09-01"
    )

    assert attr.shoe.id == "vomero"
    assert attr.how == BY_DEFAULT
