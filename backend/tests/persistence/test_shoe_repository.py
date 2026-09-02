from app.domain.entities.shoe import Shoe, ShoeBook, canonical_category
from app.infrastructure.persistence.shoe_repository import ShoeRepository


def _repo(tmp_path) -> ShoeRepository:

    repo = ShoeRepository()
    repo.storage = tmp_path
    return repo


def test_load_heals_mojibake_category(tmp_path):
    """Dado antigo corrompido ('versÃ¡til') é curado na LEITURA -> a categoria
    volta canônica e a listagem/recomendação voltam a funcionar."""

    file = tmp_path / "atleta.json"

    file.write_text(
        '{"shoes": [{"id": "x", "name": "Corre", '
        '"category": "versÃ¡til"}]}',
        encoding="utf-8",
    )

    book = _repo(tmp_path).load("atleta")

    assert book.get("x").category == "versátil"


def test_heal_persists_on_next_save(tmp_path):
    """A cura na leitura auto-repara o disco no próximo save (round-trip limpo)."""

    repo = _repo(tmp_path)

    (tmp_path / "atleta.json").write_text(
        '{"shoes": [{"id": "x", "name": "Corre", '
        '"category": "rÃ¡pido"}]}',
        encoding="utf-8",
    )

    book = repo.load("atleta")     # cura em memória
    repo.save("atleta", book)      # grava limpo

    reloaded = repo.load("atleta")
    assert reloaded.get("x").category == "rápido"


def test_clean_category_survives_round_trip(tmp_path):
    """Categoria já correta não é mexida pela cura."""

    repo = _repo(tmp_path)

    repo.save("atleta", ShoeBook(shoes=[
        Shoe(id="x", name="Nimbus", category="dia a dia"),
        Shoe(id="y", name="Racer", category="rápido"),
    ]))

    book = repo.load("atleta")
    assert book.get("x").category == "dia a dia"
    assert book.get("y").category == "rápido"


def test_canonical_category_maps_synonyms_and_mojibake():

    assert canonical_category("prova") == "rápido"
    assert canonical_category("rÃ¡pido") == "rápido"
    assert canonical_category("super trainer") == "versátil"
    assert canonical_category("versÃ¡til") == "versátil"
    assert canonical_category("DAILY") == "dia a dia"
    assert canonical_category(None) is None
    assert canonical_category("qualquer coisa") is None
