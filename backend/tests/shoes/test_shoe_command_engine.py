import asyncio
from unittest.mock import AsyncMock, patch

from app.application.shoes.shoe_command_engine import ShoeCommandEngine
from app.domain.entities.shoe import Shoe, ShoeBook
from app.infrastructure.persistence.shoe_repository import ShoeRepository
from tests.coach.factories import make_runner

MOD = "app.application.shoes.shoe_command_engine"
WEB = "app.application.shoes.shoe_web_lookup.ShoeWebLookup.classify_many"

PROFILE = "renato"


def _real_repo(tmp_path) -> ShoeRepository:

    repo = ShoeRepository()
    repo.storage = tmp_path
    return repo


def _handle(tmp_path, parsed, seed_book=None, web=None, web_mock=None):

    repo = _real_repo(tmp_path)

    if seed_book is not None:

        repo.save(PROFILE, seed_book)

    runner = make_runner(name="Renato")

    classify = web_mock or AsyncMock(return_value=web or {})

    with (
        patch(f"{MOD}.ShoeRepository", return_value=repo),
        patch(f"{MOD}.generate_json", new=AsyncMock(return_value=parsed)),
        patch(WEB, new=classify),
    ):

        reply = asyncio.run(
            ShoeCommandEngine.handle(PROFILE, runner, "qualquer texto")
        )

    return reply, repo.load(PROFILE)


def test_register_shoes_research_classifies_and_default_set(tmp_path):
    """O parse só extrai nome/km/default; a FUNÇÃO vem da pesquisa web."""

    parsed = {
        "reply": "Anotado!",
        "ops": [
            {"op": "add", "name": "Adidas Boston", "nickname": "Boston",
             "initial_km": 200, "default": True},
            {"op": "add", "name": "Nike Vaporfly", "nickname": "Vaporfly",
             "initial_km": 0, "default": False},
        ],
        "show_status": True,
    }

    web = {
        "adidas boston": {"category": "dia a dia", "threshold_km": 650.0},
        "nike vaporfly": {"category": "prova", "threshold_km": 450.0},
    }

    reply, book = _handle(tmp_path, parsed, web=web)

    assert len(book.active()) == 2
    boston = book.get("adidas-boston")
    assert boston.is_default and boston.initial_km == 200
    assert boston.category == "dia a dia"
    assert book.get("nike-vaporfly").category == "prova"
    assert book.get("nike-vaporfly").alert_threshold_km == 450.0
    assert "Boston" in reply and "200 km" in reply


def test_ensure_default_picks_a_daily_when_none_marked(tmp_path):
    """Atleta não disse qual é o do dia a dia -> escolhe um 'dia a dia'."""

    parsed = {
        "reply": "ok", "show_status": False,
        "ops": [
            {"op": "add", "name": "Vaporfly", "default": False},
            {"op": "add", "name": "Boston", "default": False},
        ],
    }

    web = {
        "vaporfly": {"category": "prova", "threshold_km": 450.0},
        "boston": {"category": "dia a dia", "threshold_km": 650.0},
    }

    _, book = _handle(tmp_path, parsed, web=web)

    assert book.get("boston").is_default is True
    assert book.get("vaporfly").is_default is False


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


def test_recategorize_changes_function_and_wear(tmp_path):
    """'os Evo SL são de prova' -> muda categoria + vida útil, sem tocar km."""

    seed = ShoeBook(shoes=[
        Shoe(id="evo", name="Evo SL", category="dia a dia",
             alert_threshold_km=650.0, is_default=True),
    ])

    parsed = {"reply": "Corrigi!", "ops": [
        {"op": "recategorize", "shoe": "evo", "category": "prova"}],
        "show_status": False}

    _, book = _handle(tmp_path, parsed, seed)

    assert book.get("evo").category == "prova"
    assert book.get("evo").alert_threshold_km == 450.0


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


def test_query_does_not_call_web(tmp_path):
    """Consulta (sem par novo) não dispara pesquisa web."""

    seed = ShoeBook(shoes=[Shoe(id="boston", name="Boston", is_default=True)])

    web = AsyncMock(return_value={})

    _handle(tmp_path, {"reply": "", "ops": [], "show_status": True},
            seed, web_mock=web)

    web.assert_not_awaited()


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


def test_assign_pins_shoe_to_next_occurrence_of_day(tmp_path):
    """'quero o Red Hare no domingo' -> fixa o par na próxima data daquele dia."""

    from datetime import date

    seed = ShoeBook(shoes=[
        Shoe(id="vomero", name="Vomero", category="dia a dia", is_default=True),
        Shoe(id="red", name="Red Hare", category="dia a dia"),
    ])

    parsed = {"reply": "Fechou!", "ops": [
        {"op": "assign", "shoe": "red", "day": "Sunday"}], "show_status": False}

    # hoje = quinta 27/08 -> próximo domingo = 30/08
    with patch("app.core.clock.today_local", return_value=date(2026, 8, 27)):

        _, book = _handle(tmp_path, parsed, seed)

    assert book.assignments.get("2026-08-30") == "red"


def test_research_fills_category_for_new_shoe(tmp_path):

    parsed = {
        "reply": "Registrei!",
        "ops": [{"op": "add", "name": "Marca Obscura Z1", "default": True}],
        "show_status": False,
    }

    web = {"marca obscura z1": {"category": "prova", "threshold_km": 430.0}}

    _, book = _handle(tmp_path, parsed, web=web)

    shoe = book.get("marca-obscura-z1")
    assert shoe.category == "prova"
    assert shoe.alert_threshold_km == 430.0
