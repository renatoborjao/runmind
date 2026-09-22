import pytest

from app.infrastructure.persistence.activity_comment_repository import (
    ActivityCommentRepository,
)


@pytest.fixture
def repo(tmp_path):
    r = ActivityCommentRepository()
    r.dir = tmp_path / "comments"
    r.dir.mkdir(parents=True, exist_ok=True)
    return r


def test_add_list_and_count(repo):
    repo.add("helio", "arch-1", "renato2", "Renato", "Voa demais! 🔥")
    repo.add("helio", "arch-1", "fernanda", "Fernanda", "Que ritmo!")
    repo.add("helio", "arch-2", "renato2", "Renato", "👏")

    lst = repo.list("helio", "arch-1")
    assert [c["author_name"] for c in lst] == ["Renato", "Fernanda"]
    assert all(c["id"] and c["at"] for c in lst)

    assert repo.counts("helio") == {"arch-1": 2, "arch-2": 1}


def test_author_can_delete_own(repo):
    c = repo.add("helio", "arch-1", "renato2", "Renato", "ops")
    assert repo.delete("helio", "arch-1", c["id"], "renato2") is True
    assert repo.list("helio", "arch-1") == []


def test_owner_can_moderate(repo):
    c = repo.add("helio", "arch-1", "renato2", "Renato", "spam")
    # o dono da atividade (helio) apaga comentário de outro
    assert repo.delete("helio", "arch-1", c["id"], "helio") is True


def test_stranger_cannot_delete(repo):
    c = repo.add("helio", "arch-1", "renato2", "Renato", "meu")
    assert repo.delete("helio", "arch-1", c["id"], "fernanda") is False
    assert len(repo.list("helio", "arch-1")) == 1


def test_text_trimmed_and_capped(repo):
    c = repo.add("helio", "arch-1", "x", "X", "  " + "a" * 800 + "  ")
    assert len(c["text"]) == 500
