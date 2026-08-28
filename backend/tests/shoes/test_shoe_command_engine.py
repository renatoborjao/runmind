import asyncio
from unittest.mock import AsyncMock, patch

from app.application.shoes.shoe_command_engine import ShoeCommandEngine
from app.domain.entities.shoe import Shoe, ShoeBook
from app.infrastructure.persistence.shoe_repository import ShoeRepository
from tests.coach.factories import make_runner

MOD = "app.application.shoes.shoe_command_engine"

PROFILE = "renato"


def _real_repo(tmp_path) -> ShoeRepository:

    repo = ShoeRepository()
    repo.storage = tmp_path
    return repo


def _handle(tmp_path, parsed, seed_book=None):

    repo = _real_repo(tmp_path)

    if seed_book is not None:

        repo.save(PROFILE, seed_book)

    runner = make_runner(name="Renato")

    with (
        patch(f"{MOD}.ShoeRepository", return_value=repo),
        patch(f"{MOD}.generate_json", new=AsyncMock(return_value=parsed)),
    ):

        reply = asyncio.run(
            ShoeCommandEngine.handle(PROFILE, runner, "qualquer texto")
        )

    return reply, repo.load(PROFILE)


def test_register_two_shoes_sets_default_and_initial_km(tmp_path):

    parsed = {
        "reply": "Anotado!",
        "ops": [
            {"op": "add", "name": "Adidas Boston", "nickname": "Boston",
             "category": "dia a dia", "initial_km": 200, "default": True},
            {"op": "add", "name": "Nike Vaporfly", "nickname": "Vaporfly",
             "category": "prova", "initial_km": 0, "default": False},
        ],
        "show_status": True,
    }

    reply, book = _handle(tmp_path, parsed)

    assert len(book.active()) == 2
    boston = book.get("adidas-boston")
    assert boston.is_default and boston.initial_km == 200
    assert book.get("nike-vaporfly").is_default is False
    # status com km EXATO do armário
    assert "Boston" in reply and "200 km" in reply


def test_set_default_switches_daily_shoe(tmp_path):

    seed = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", is_default=True),
        Shoe(id="novo", name="Novo Par"),
    ])

    parsed = {"reply": "Fechou!", "ops": [
        {"op": "set_default", "shoe": "novo"}], "show_status": False}

    _, book = _handle(tmp_path, parsed, seed)

    assert book.get("novo").is_default is True
    assert book.get("boston").is_default is False


def test_rule_adds_rotation(tmp_path):

    seed = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", is_default=True),
        Shoe(id="vapor", name="Vaporfly"),
    ])

    parsed = {"reply": "Anotado o rodízio!", "ops": [
        {"op": "rule", "match": "tiro", "shoe": "vapor"}], "show_status": False}

    _, book = _handle(tmp_path, parsed, seed)

    assert any(r.match == "tiro" and r.shoe_id == "vapor" for r in book.rules)


def test_query_shows_exact_km_without_ops(tmp_path):

    seed = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", nickname="Boston", is_default=True,
             initial_km=100.0, accumulated_km=53.4),
    ])

    parsed = {"reply": "", "ops": [], "show_status": True}

    reply, _ = _handle(tmp_path, parsed, seed)

    assert "Boston" in reply
    assert "153 km" in reply  # 100 + 53.4 -> arredonda 153


def test_correct_last_moves_km_between_shoes(tmp_path):

    seed = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", is_default=True,
                 accumulated_km=50.0, counted_ids=[99]),
            Shoe(id="vapor", name="Vaporfly", accumulated_km=0.0),
        ],
        last_activity_id=99, last_shoe_id="boston", last_km=10.0,
    )

    parsed = {"reply": "Corrigido!", "ops": [
        {"op": "correct_last", "shoe": "vapor"}], "show_status": False}

    _, book = _handle(tmp_path, parsed, seed)

    assert book.get("boston").accumulated_km == 40.0
    assert book.get("vapor").accumulated_km == 10.0
    assert 99 in book.get("vapor").counted_ids
    assert 99 not in book.get("boston").counted_ids


def test_retire_removes_from_active_and_default(tmp_path):

    seed = ShoeBook(shoes=[Shoe(id="boston", name="Boston", is_default=True)])

    parsed = {"reply": "Aposentado!", "ops": [
        {"op": "retire", "shoe": "boston"}], "show_status": False}

    _, book = _handle(tmp_path, parsed, seed)

    assert book.get("boston").retired is True
    assert book.active() == []


def test_ai_failure_returns_none(tmp_path):

    reply, _ = _handle(tmp_path, None)

    assert reply is None
