from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.infrastructure.security.session_token import SessionToken


def current_profile(request: Request) -> str:
    """Identidade do atleta logado, tirada do cookie de sessão assinado.

    É a ÚNICA fonte de verdade de 'quem sou eu' nas rotas protegidas — nada de
    `?profile=` (qualquer um veria o plano de qualquer um). 401 se não há sessão
    válida."""

    cookie_name = get_settings().auth_cookie_name

    profile = SessionToken.verify(request.cookies.get(cookie_name))

    if not profile:

        raise HTTPException(status_code=401, detail="Não autenticado")

    return profile
