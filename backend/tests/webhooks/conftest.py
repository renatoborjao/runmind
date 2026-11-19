"""Os testes de roteamento daqui são sobre "número novo → cadastro": o cadastro
por mensagem é fechado por convite, então eles chegam com um convite válido.
A trava em si é testada em tests/auth/test_blocked_athlete.py."""

import pytest


@pytest.fixture(autouse=True)
def _valid_invite(monkeypatch):

    from app.infrastructure.persistence.invite_code_repository import (
        InviteCodeRepository,
    )

    monkeypatch.setattr(InviteCodeRepository, "find_in_text", lambda self, text: "RIT-TEST")
