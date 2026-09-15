from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.application.auth.magic_link_service import MagicLinkService
from app.application.auth.signup_service import SignupError, SignupService
from app.core.config import get_settings
from app.infrastructure.security.session_token import SessionToken
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):

    email: str


class SignupRequest(BaseModel):

    email: str

    invite_code: str


class VerifyRequest(BaseModel):

    token: str


def _set_session_cookie(response: Response, session: str) -> None:

    settings = get_settings()

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session,
        max_age=settings.auth_session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        path="/",
    )


@router.post("/request")
async def request_login(body: LoginRequest):
    """Pede um magic link. Resposta SEMPRE genérica (não revela se o e-mail
    está cadastrado — evita enumeração de contas)."""

    MagicLinkService.request_login(body.email)

    return {
        "ok": True,
        "message": "Se este e-mail estiver cadastrado, enviamos um link de acesso.",
    }


@router.post("/signup")
async def signup(body: SignupRequest, response: Response):
    """Auto-cadastro por convite (beta fechado). Convite inválido → 400. Atleta
    NOVO: cria a conta e já LOGA (o convite é a garantia; não depende de e-mail).
    E-mail que já tem conta: não loga (segurança) e devolve `logged_in=False` —
    o app manda pra tela de Entrar."""

    try:

        result = SignupService.start(body.email, body.invite_code)

    except SignupError as e:

        raise HTTPException(status_code=400, detail=str(e)) from e

    if result["status"] == "created":

        _set_session_cookie(response, SessionToken.issue(result["profile"]))

        return {"ok": True, "logged_in": True}

    # e-mail já cadastrado: manda entrar (não logamos com base só no convite)
    return {
        "ok": True,
        "logged_in": False,
        "message": "Essa conta já existe. Entra pela tela de acesso.",
    }


@router.post("/verify")
async def verify_login(body: VerifyRequest, response: Response):
    """Troca o magic token por uma sessão logada (cookie). O frontend chama isto
    a partir da página /entrar?token=..."""

    session = MagicLinkService.verify(body.token)

    if not session:

        raise HTTPException(status_code=400, detail="Link inválido ou expirado")

    _set_session_cookie(response, session)

    return {"ok": True}


@router.get("/me")
async def me(profile: str = Depends(current_profile)):
    """Dados básicos do atleta logado (pra o app saber quem é)."""

    runner = RunnerProfileRepository().load(profile)

    return {
        "profile": profile,
        "name": runner.name,
        "email": runner.email,
        "goal": runner.goal,
        "onboarding_complete": runner.onboarding_complete,
    }


@router.post("/logout")
async def logout(response: Response):

    response.delete_cookie(
        key=get_settings().auth_cookie_name,
        path="/",
    )

    return {"ok": True}
