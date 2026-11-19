"""Atleta DESLIGADO só volta por convite: mensagem não reabre cadastro (nem IA),
sessão antiga cai em 401, e o cadastro com convite tira o bloqueio."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.application.auth import signup_service
from app.application.auth.signup_service import SignupService
from app.application.onboarding import onboarding_flow
from app.infrastructure.persistence.invite_code_repository import (
    InviteCodeRepository,
)
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.core.config import get_settings
from app.infrastructure.persistence.blocked_athlete_repository import (
    BlockedAthleteRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.security.session_token import SessionToken
from app.presentation.api.deps import current_profile
from app.presentation.api.v1 import webhooks

PROFILE = {
    "name": "Fulano", "email": "Fulano@Ex.com", "telegram_id": 777,
    "phone": "+55 (11) 90000-0000", "strava_athlete_id": 42,
}


def _block():

    return BlockedAthleteRepository().block("fulano", PROFILE, reason="sem uso")


def test_block_normalizes_and_finds_by_address():

    entry = _block()
    repo = BlockedAthleteRepository()

    assert entry["email"] == "fulano@ex.com"
    assert repo.find_by_address("telegram", "777") == "fulano"
    assert repo.find_by_address("whatsapp", "5511900000000") == "fulano"
    assert repo.find_by_address("telegram", "888") is None
    assert repo.is_slug_blocked("fulano")


def test_notice_only_once_per_window():

    _block()
    repo = BlockedAthleteRepository()

    assert repo.should_notify("fulano") is True
    assert repo.should_notify("fulano") is False


def test_blocked_telegram_does_not_start_onboarding():

    _block()

    with (
        patch.object(webhooks, "RunnerProfileRepository") as repo_cls,
        patch.object(webhooks, "OnboardingEvent") as onboarding,
        patch.object(webhooks, "NotificationService") as notif,
    ):

        repo_cls.return_value.find_by_telegram_id.return_value = None
        onboarding.execute = AsyncMock()
        notif.send_to = AsyncMock()

        first = asyncio.run(webhooks.route_inbound("telegram", "777", "oi", None, "F"))
        second = asyncio.run(webhooks.route_inbound("telegram", "777", "oi", None, "F"))

    onboarding.execute.assert_not_called()
    assert first["blocked"] and first["reply_sent"]
    assert second["blocked"] and not second["reply_sent"]
    notif.send_to.assert_awaited_once()
    assert notif.send_to.await_args.kwargs["message"] == webhooks.BLOCKED_NOTICE


@pytest.fixture
def invites(monkeypatch):
    """Convites num arquivo temporário, com um válido (RIT-AB23)."""

    repo = InviteCodeRepository.__new__(InviteCodeRepository)
    repo.storage = Path(__import__("tempfile").mkdtemp())
    repo.file = repo.storage / "invite_codes.json"
    repo.file.write_text(json.dumps({"RIT-AB23": {"max_uses": 1, "uses": 0}}))

    for mod in (webhooks, onboarding_flow):
        monkeypatch.setattr(mod, "InviteCodeRepository", lambda: repo)

    return repo


def _route(address, text, onboarding_reply="Como você se chama?"):

    with (
        patch.object(webhooks, "RunnerProfileRepository") as repo_cls,
        patch.object(webhooks, "OnboardingEvent") as onboarding,
        patch.object(webhooks, "NotificationService") as notif,
    ):

        repo_cls.return_value.find_by_telegram_id.return_value = None
        notif.send_to = AsyncMock()

        async def _start(**kw):
            # o fluxo real cria o estado do cadastro na 1ª mensagem
            OnboardingStateRepository().save(kw["address"], {"step": "ASK_NAME"})
            return onboarding_reply

        onboarding.execute = AsyncMock(side_effect=_start)

        result = asyncio.run(webhooks.route_inbound("telegram", address, text, None, "F"))

    return result, onboarding.execute, notif.send_to


def test_unknown_without_invite_gets_fixed_reply_no_onboarding(invites):

    result, onboarding, send = _route("999", "/start")

    assert result["needs_invite"]
    onboarding.assert_not_called()
    assert send.await_args.kwargs["message"] == webhooks.INVITE_REQUIRED_NOTICE
    assert OnboardingStateRepository().load("999") is None


def test_unknown_with_invite_onboards_and_keeps_code(invites):

    result, onboarding, _ = _route("999", "/start rit-ab23")

    assert result["onboarding"]
    onboarding.assert_awaited_once()
    assert OnboardingStateRepository().load("999")["invite_code"] == "RIT-AB23"
    # não consome ainda: só quando o perfil nasce
    assert invites.validate("RIT-AB23")


def test_onboarding_in_progress_continues_without_invite(invites):

    OnboardingStateRepository().save("999", {"step": "ASK_AGE"})

    result, onboarding, _ = _route("999", "34")

    assert result["onboarding"]
    onboarding.assert_awaited_once()


def test_invalid_or_used_invite_is_refused(invites):

    invites.consume("RIT-AB23")

    result, onboarding, _ = _route("999", "RIT-AB23")

    assert result["needs_invite"]
    onboarding.assert_not_called()


def test_blocked_athlete_with_invite_comes_back(invites):

    _block()

    result, onboarding, _ = _route("777", "meu convite: RIT AB23")

    assert result["onboarding"]
    onboarding.assert_awaited_once()
    assert not BlockedAthleteRepository().is_slug_blocked("fulano")


def _request_with_session(slug):

    cookie = f"{get_settings().auth_cookie_name}={SessionToken.issue(slug)}"

    return Request({
        "type": "http", "method": "GET", "path": "/",
        "headers": [(b"cookie", cookie.encode())],
    })


def test_old_session_of_blocked_athlete_is_401():

    assert current_profile(_request_with_session("fulano")) == "fulano"

    _block()

    with pytest.raises(HTTPException) as exc:

        current_profile(_request_with_session("fulano"))

    assert exc.value.status_code == 401


@pytest.fixture
def signup_env(tmp_path, monkeypatch):

    profiles = RunnerProfileRepository()
    profiles.storage = tmp_path / "profiles"
    profiles.storage.mkdir()
    monkeypatch.setattr(signup_service, "RunnerProfileRepository", lambda: profiles)

    invites = type("Inv", (), {
        "validate": lambda self, c: c == "OK",
        "consume": lambda self, c: True,
    })()
    monkeypatch.setattr(signup_service, "InviteCodeRepository", lambda: invites)
    monkeypatch.setattr(SignupService, "_send_code", staticmethod(lambda *a: None))

    return profiles


def test_invite_signup_unblocks_and_reuses_slug(signup_env):

    _block()

    result = SignupService.start("fulano@ex.com", "OK")

    assert result == {"status": "created", "profile": "fulano"}
    assert not BlockedAthleteRepository().is_slug_blocked("fulano")


def test_someone_else_does_not_take_blocked_slug(signup_env):

    _block()

    result = SignupService.start("fulano@outro.com", "OK")

    assert result["profile"] == "fulano2"
    assert BlockedAthleteRepository().is_slug_blocked("fulano")
