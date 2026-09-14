from types import SimpleNamespace
from unittest.mock import patch

from app.application.auth.magic_link_service import MagicLinkService
from app.infrastructure.security.session_token import SessionToken

MOD = "app.application.auth.magic_link_service"


class _FakeTokens:
    """Repo de magic tokens em memória, compartilhado entre instâncias (issue no
    request e consume no verify caem no mesmo store)."""

    store: dict = {}

    def issue(self, profile, ttl_minutes):

        _FakeTokens.store["tok-123"] = profile

        return "tok-123"

    def consume(self, token):

        return _FakeTokens.store.pop(token, None)


class _FakeProfiles:

    def __init__(self, email_owner):

        self._owner = email_owner

    def find_by_email(self, email):

        return self._owner

    def load(self, profile):

        return SimpleNamespace(name="Renato Teste", email="a@b.com")


def _run_request(email, owner):

    sent = {}

    def _capture(to, subject, text, html=None):

        sent["to"] = to
        sent["text"] = text
        return True

    with (
        patch(f"{MOD}.AuthTokenRepository", _FakeTokens),
        patch(f"{MOD}.RunnerProfileRepository", lambda: _FakeProfiles(owner)),
        patch(f"{MOD}.EmailSender.send", side_effect=_capture),
    ):

        MagicLinkService.request_login(email)

    return sent


def test_known_email_sends_link_with_token():

    _FakeTokens.store = {}

    sent = _run_request("a@b.com", owner="renato2")

    assert sent.get("to") == "a@b.com"
    assert "tok-123" in sent["text"]
    assert "/entrar?token=" in sent["text"]


def test_unknown_email_sends_nothing():

    _FakeTokens.store = {}

    sent = _run_request("ninguem@x.com", owner=None)

    assert sent == {}  # EmailSender.send nunca chamado


def test_verify_consumes_token_and_issues_session():

    _FakeTokens.store = {"tok-123": "renato2"}

    with patch(f"{MOD}.AuthTokenRepository", _FakeTokens):

        session = MagicLinkService.verify("tok-123")

    assert session is not None
    assert SessionToken.verify(session) == "renato2"


def test_verify_bad_token_returns_none():

    _FakeTokens.store = {}

    with patch(f"{MOD}.AuthTokenRepository", _FakeTokens):

        assert MagicLinkService.verify("nao-existe") is None
