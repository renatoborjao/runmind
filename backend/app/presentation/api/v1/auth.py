from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.application.auth.google_auth_service import (
    GoogleAuthError,
    GoogleAuthService,
    GoogleNeedsInvite,
)
from app.application.auth.magic_link_service import MagicLinkService
from app.application.auth.password_auth_service import (
    LoginLocked,
    PasswordAuthService,
    PasswordError,
)
from app.application.auth.signup_service import SignupError, SignupService
from app.infrastructure.persistence.credential_repository import (
    CredentialRepository,
)
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

    # opcional só pra não quebrar app antigo em cache; o app novo sempre manda
    password: str | None = None


class PasswordLogin(BaseModel):

    email: str

    password: str


class PasswordChange(BaseModel):

    new_password: str

    current_password: str | None = None


class PasswordReset(BaseModel):

    reset_token: str

    new_password: str


class GoogleLogin(BaseModel):

    credential: str

    invite_code: str | None = None


# depois de provar que é o dono por link/código (e-mail ou coach no Telegram),
# o atleta tem esse tempo pra definir uma senha nova sem saber a antiga
RESET_PURPOSE = "password_reset"

_RESET_TTL_SECONDS = 15 * 60


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

        result = SignupService.start(
            body.email, body.invite_code, password=body.password,
        )

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


@router.post("/login")
async def login(body: PasswordLogin, response: Response):
    """E-mail + senha -> sessão. Erro genérico (não revela se o e-mail existe);
    muitas tentativas erradas travam o e-mail por um tempo (429)."""

    try:

        profile = PasswordAuthService.login(body.email, body.password)

    except LoginLocked as e:

        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Espera uns minutos e tenta de novo.",
            headers={"Retry-After": str(e.retry_after)},
        ) from e

    if not profile:

        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    _set_session_cookie(response, SessionToken.issue(profile))

    return {"ok": True}


@router.post("/google")
async def google_login(body: GoogleLogin, response: Response):
    """Entrar com Google. Conta existente (pelo Google ou pelo mesmo e-mail)
    entra direto; conta nova precisa do convite -> `needs_invite` (o app pede o
    código e chama de novo com a mesma credencial)."""

    try:

        result = await GoogleAuthService.authenticate(
            body.credential, body.invite_code,
        )

    except GoogleNeedsInvite:

        return {"ok": False, "needs_invite": True}

    except GoogleAuthError as e:

        raise HTTPException(status_code=401, detail=str(e)) from e

    except SignupError as e:

        raise HTTPException(status_code=400, detail=str(e)) from e

    _set_session_cookie(response, SessionToken.issue(result["profile"]))

    return {"ok": True, "created": result["created"]}


@router.get("/config")
async def auth_config():
    """O que o app precisa pra montar a tela de login (sem rebuild do front)."""

    return {"google_client_id": get_settings().google_client_id.strip() or None}


@router.post("/password")
async def change_password(
    body: PasswordChange, profile: str = Depends(current_profile),
):
    """Cria (1ª vez) ou troca a senha do atleta logado. Trocar exige a atual."""

    try:

        PasswordAuthService.set_password(
            profile, body.new_password, body.current_password,
        )

    except PasswordError as e:

        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"ok": True}


@router.post("/password/reset")
async def reset_password(body: PasswordReset):
    """Senha nova sem a antiga — só com o `reset_token` que o /verify entrega
    (o atleta acabou de provar que é o dono por link/código)."""

    profile = SessionToken.verify(body.reset_token, purpose=RESET_PURPOSE)

    if not profile:

        raise HTTPException(
            status_code=400,
            detail="Esse acesso venceu. Peça um novo link pra redefinir a senha.",
        )

    try:

        PasswordAuthService.reset_password(profile, body.new_password)

    except PasswordError as e:

        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"ok": True}


@router.post("/verify")
async def verify_login(body: VerifyRequest, response: Response):
    """Troca o magic token por uma sessão logada (cookie). O frontend chama isto
    a partir da página /entrar?token=..."""

    session = MagicLinkService.verify(body.token)

    if not session:

        raise HTTPException(status_code=400, detail="Link inválido ou expirado")

    _set_session_cookie(response, session)

    profile = SessionToken.verify(session)

    reset_token = SessionToken.issue(
        profile, purpose=RESET_PURPOSE, ttl_seconds=_RESET_TTL_SECONDS,
    )

    return {
        "ok": True,
        "reset_token": reset_token,
        "has_password": PasswordAuthService.has_password(profile),
    }


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
        # formas de acesso (o Perfil oferece criar senha / mostra o Google)
        "has_password": PasswordAuthService.has_password(profile),
        "google_linked": bool(CredentialRepository().google_sub(profile)),
    }


@router.post("/logout")
async def logout(response: Response):

    response.delete_cookie(
        key=get_settings().auth_cookie_name,
        path="/",
    )

    return {"ok": True}
