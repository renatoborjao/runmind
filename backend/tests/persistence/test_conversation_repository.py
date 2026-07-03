from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)


def _isolated_repo(tmp_path):

    repo = ConversationRepository()

    repo.storage = tmp_path

    return repo


def test_load_returns_empty_list_when_no_file(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.load("renato") == []


def test_append_turn_persists_role_text_and_timestamp(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.append_turn("renato", role="user", text="Bom dia coach")

    turns = repo.load("renato")

    assert len(turns) == 1
    assert turns[0]["role"] == "user"
    assert turns[0]["text"] == "Bom dia coach"
    assert "timestamp" in turns[0]


def test_append_turn_truncates_to_last_200(tmp_path):

    repo = _isolated_repo(tmp_path)

    for i in range(205):

        repo.append_turn("renato", role="user", text=f"turno {i}")

    turns = repo.load("renato")

    assert len(turns) == 200
    assert turns[0]["text"] == "turno 5"
    assert turns[-1]["text"] == "turno 204"


def test_recent_turns_respects_limit(tmp_path):

    repo = _isolated_repo(tmp_path)

    for i in range(30):

        repo.append_turn("renato", role="user", text=f"turno {i}")

    recent = repo.recent_turns("renato", limit=5)

    assert len(recent) == 5
    assert recent[-1]["text"] == "turno 29"
