"""Entrar com Google (Google Identity Services). O app recebe do Google um ID
token (JWT assinado pelo Google) e manda pra cá; a gente confere com o próprio
Google (endpoint tokeninfo — sem biblioteca nova) que ele é válido, foi emitido
PRO NOSSO app (aud = nosso Client ID) e que o e-mail está verificado.

Quem é o atleta:
1. conta já ligada a esse Google (google_sub)       -> entra;
2. perfil com o MESMO e-mail (verificado pelo Google) -> liga o Google e entra
   (atleta do Telegram que cadastrou e-mail cai aqui);
3. ninguém: conta nova — só com convite (beta fechado).
"""

from __future__ import annotations

import httpx

from app.application.auth.signup_service import SignupError, SignupService
from app.core.config import get_settings
from app.infrastructure.persistence.credential_repository import (
    CredentialRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleAuthError(Exception):
    """Token do Google inválido/de outro app, ou login Google desligado."""


class GoogleNeedsInvite(Exception):
    """Google válido, mas sem conta — precisa do convite pra criar."""


async def verify_id_token(credential: str) -> dict:
    """{sub, email, name} do ID token, validado pelo Google. Levanta
    GoogleAuthError se não serve."""

    client_id = get_settings().google_client_id.strip()

    if not client_id:

        raise GoogleAuthError("login com Google desligado")

    if not credential:

        raise GoogleAuthError("token vazio")

    async with httpx.AsyncClient(timeout=10) as client:

        response = await client.get(TOKENINFO_URL, params={"id_token": credential})

    if response.status_code != 200:

        raise GoogleAuthError("token do Google inválido ou vencido")

    info = response.json()

    if info.get("aud") != client_id:

        raise GoogleAuthError("token emitido pra outro app")

    if info.get("iss") not in _ISSUERS:

        raise GoogleAuthError("emissor inválido")

    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):

        raise GoogleAuthError("e-mail do Google não verificado")

    return {
        "sub": str(info["sub"]),
        "email": str(info["email"]).strip().lower(),
        "name": (info.get("name") or "").strip(),
    }


class GoogleAuthService:

    @staticmethod
    async def authenticate(credential: str, invite_code: str | None = None) -> dict:
        """{"profile", "created"}. Levanta GoogleAuthError (token ruim),
        GoogleNeedsInvite (sem conta e sem convite) ou SignupError (convite
        inválido)."""

        info = await verify_id_token(credential)

        creds = CredentialRepository()

        profile = creds.find_by_google_sub(info["sub"])

        if profile:

            return {"profile": profile, "created": False}

        profile = RunnerProfileRepository().find_by_email(info["email"])

        if profile:

            creds.link_google(profile, info["sub"], info["email"])

            return {"profile": profile, "created": False}

        if not (invite_code or "").strip():

            raise GoogleNeedsInvite()

        result = SignupService.start(
            info["email"], invite_code, name=info["name"] or None,
        )

        if result["status"] != "created":  # corrida: alguém criou nesse meio-tempo

            raise SignupError("essa conta já existe — tente entrar de novo")

        creds.link_google(result["profile"], info["sub"], info["email"])

        return {"profile": result["profile"], "created": True}
