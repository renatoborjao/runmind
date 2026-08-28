from app.application.shoes.shoe_attribution_resolver import (
    BY_DEFAULT,
    BY_GEAR,
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
