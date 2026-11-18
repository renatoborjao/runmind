"""Atleta DESLIGADO só volta por convite: mensagem não reabre cadastro (nem IA),
sessão antiga cai em 401, e o cadastro com convite tira o bloqueio."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.application.auth import signup_service
from app.application.auth.signup_service import SignupService
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


def test_unknown_not_blocked_still_onboards():

    with (
        patch.object(webhooks, "RunnerProfileRepository") as repo_cls,
        patch.object(webhooks, "OnboardingEvent") as onboarding,
        patch.object(webhooks, "NotificationService"),
    ):

        repo_cls.return_value.find_by_telegram_id.return_value = None
        onboarding.execute = AsyncMock(return_value="oi")

        result = asyncio.run(webhooks.route_inbound("telegram", "999", "oi", None, "F"))

    onboarding.execute.assert_awaited_once()
    assert result["onboarding"]


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
