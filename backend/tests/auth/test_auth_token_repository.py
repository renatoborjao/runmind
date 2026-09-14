import tempfile
from pathlib import Path

from app.infrastructure.persistence.auth_token_repository import (
    AuthTokenRepository,
)


def _repo(tmp: str) -> AuthTokenRepository:

    repo = AuthTokenRepository()
    repo.storage = Path(tmp)
    repo.file = Path(tmp) / "magic_tokens.json"
    return repo


def test_issue_then_consume_once():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        token = repo.issue("helio", ttl_minutes=20)

        assert repo.consume(token) == "helio"


def test_single_use_second_consume_is_none():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        token = repo.issue("helio", ttl_minutes=20)

        assert repo.consume(token) == "helio"
        assert repo.consume(token) is None  # já queimado


def test_expired_token_is_not_consumable():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        token = repo.issue("helio", ttl_minutes=-1)  # já nasce vencido

        assert repo.consume(token) is None


def test_unknown_token_is_none():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        assert repo.consume("nao-existe") is None
        assert repo.consume("") is None


def test_issue_code_is_short_typeable_and_single_use():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        code = repo.issue_code("helio", ttl_minutes=20)

        # 6 chars, só do alfabeto sem ambiguidade (nada de 0/O/1/I/L)
        assert len(code) == 6
        assert all(c in AuthTokenRepository._CODE_ALPHABET for c in code)
        assert "0" not in code and "O" not in code and "1" not in code

        assert repo.consume(code) == "helio"
        assert repo.consume(code) is None  # uso único


def test_code_and_token_coexist():

    with tempfile.TemporaryDirectory() as tmp:

        repo = _repo(tmp)

        token = repo.issue("helio", ttl_minutes=20)
        code = repo.issue_code("helio", ttl_minutes=20)

        # os dois valem (formas diferentes de resgatar o mesmo acesso)
        assert repo.consume(code) == "helio"
        assert repo.consume(token) == "helio"
