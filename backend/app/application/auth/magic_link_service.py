from __future__ import annotations

import re

from app.core.config import get_settings
from app.infrastructure.integrations.email.email_sender import EmailSender
from app.infrastructure.persistence.auth_token_repository import (
    AuthTokenRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.security.session_token import SessionToken


class MagicLinkService:
    """Login sem senha por e-mail. Fluxo:

    1. request_login(email) — acha o atleta dono do e-mail, cria um magic token
       de uso único e manda o link por e-mail. SEMPRE devolve o mesmo sucesso
       genérico (não revela se o e-mail existe — evita enumeração de contas).
    2. verify(token) — queima o token e, se válido, emite o token de SESSÃO
       (cookie) do atleta.

    Ver [[project_reconciliacao_coach]] pro padrão de TTL curto de uso único."""

    @staticmethod
    def request_login(email: str) -> None:

        email = (email or "").strip().lower()

        if not email or "@" not in email:

            return

        profile = RunnerProfileRepository().find_by_email(email)

        if not profile:

            # e-mail não cadastrado: não faz nada (mas o endpoint responde igual)
            return

        settings = get_settings()

        token = AuthTokenRepository().issue(
            profile,
            ttl_minutes=settings.auth_magic_ttl_minutes,
        )

        link = f"{settings.app_base_url.rstrip('/')}/entrar?token={token}"

        runner = RunnerProfileRepository().load(profile)

        first_name = (runner.name or "").split(" ")[0] or "corredor"

        subject = "Seu acesso ao Ritmind 🏃"

        body_text = (
            f"Fala, {first_name}!\n\n"
            "Toque no link abaixo pra entrar no Ritmind (vale por "
            f"{settings.auth_magic_ttl_minutes} minutos, uso único):\n\n"
            f"{link}\n\n"
            "Se não foi você que pediu, é só ignorar este e-mail.\n\n"
            "— Ritmind"
        )

        body_html = (
            f"<p>Fala, {first_name}!</p>"
            "<p>Toque no botão pra entrar no <b>Ritmind</b> — vale por "
            f"{settings.auth_magic_ttl_minutes} minutos, uso único.</p>"
            f'<p><a href="{link}" style="display:inline-block;background:#0FB499;'
            'color:#062b25;font-weight:700;text-decoration:none;padding:12px 22px;'
            'border-radius:12px;font-family:sans-serif">Entrar no Ritmind</a></p>'
            f'<p style="color:#8A8B9E;font-size:12px">Ou cole no navegador:<br>{link}</p>'
            '<p style="color:#8A8B9E;font-size:12px">Se não foi você que pediu, '
            "ignore este e-mail.</p>"
        )

        EmailSender.send(email, subject, body_text, body_html)

    @staticmethod
    def verify(token: str) -> str | None:
        """Consome o magic token e, se válido, devolve o TOKEN DE SESSÃO
        (cookie) do atleta. None se o token é inválido/vencido/já usado.

        Aceita as DUAS formas: o token longo do link (?token=) E o CÓDIGO curto
        que o atleta digita no app (ex.: "ABC-DEF" → "ABCDEF"). Tenta o valor
        cru primeiro (link); se falhar, normaliza como código (maiúsculas, só
        alfanumérico) e tenta de novo."""

        raw = (token or "").strip()

        if not raw:

            return None

        repo = AuthTokenRepository()

        profile = repo.consume(raw)

        if not profile:

            code = re.sub(r"[^A-Za-z0-9]", "", raw).upper()

            if code and code != raw:

                profile = repo.consume(code)

        if not profile:

            return None

        return SessionToken.issue(profile)
