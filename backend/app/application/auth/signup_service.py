"""Auto-cadastro no app (acesso fechado por convite). Fluxo:

1. `start(email, invite_code)` — valida o convite; se o e-mail JÁ tem perfil,
   manda um código de login (não revela que existe); senão cria um perfil-
   esqueleto (`channel="app"`, `onboarding_complete=False`), consome o convite e
   manda o código por e-mail. O atleta digita o código em /cadastro → sessão →
   wizard de onboarding.

Login sem senha reaproveita `AuthTokenRepository` + `SessionToken` (o /auth/verify
que já existe troca o código pela sessão). Ver [[project_app_atleta]].
"""

from __future__ import annotations

import unicodedata

from app.core.config import get_settings
from app.infrastructure.integrations.email.email_sender import EmailSender
from app.infrastructure.persistence.auth_token_repository import (
    AuthTokenRepository,
)
from app.infrastructure.persistence.invite_code_repository import (
    InviteCodeRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# código de cadastro/login vale mais que o login normal (o atleta pode demorar
# um pouco preenchendo o e-mail) — 60 min, uso único.
_SIGNUP_CODE_TTL_MIN = 60


class SignupError(Exception):
    """Convite inválido/esgotado — o cadastro não pode prosseguir."""


class SignupService:

    @staticmethod
    def start(email: str, invite_code: str) -> None:
        """Dispara o código por e-mail. Levanta `SignupError` só quando o
        CONVITE é inválido (isso a gente pode revelar — não vaza nada do
        e-mail). Se o e-mail já existe, manda código de login e volta em
        silêncio (sem revelar que a conta existe)."""

        email = (email or "").strip().lower()

        if not email or "@" not in email:

            raise SignupError("email inválido")

        invites = InviteCodeRepository()

        if not invites.validate(invite_code):

            raise SignupError("convite inválido ou esgotado")

        repo = RunnerProfileRepository()

        existing = repo.find_by_email(email)

        if existing:

            # já tem conta: manda código de LOGIN (não consome convite, não
            # revela que existe — o endpoint responde igual pros dois casos)
            SignupService._send_code(existing, email)

            return

        # novo atleta: cria o esqueleto, consome o convite e manda o código
        slug = SignupService._unique_slug(email)

        repo.save(slug, SignupService._skeleton(slug, email))

        # consome só depois de gravar o esqueleto (se algo falhar antes, o
        # convite não é queimado à toa)
        invites.consume(invite_code)

        SignupService._send_code(slug, email)

    @staticmethod
    def _send_code(profile: str, email: str) -> None:

        code = AuthTokenRepository().issue_code(
            profile,
            ttl_minutes=_SIGNUP_CODE_TTL_MIN,
        )

        pretty = f"{code[:3]}-{code[3:]}" if len(code) == 6 else code

        settings = get_settings()

        link = f"{settings.app_base_url.rstrip('/')}/entrar?token={code}"

        subject = "Seu código de acesso ao Ritmind 🏃"

        body_text = (
            "Bem-vindo ao Ritmind!\n\n"
            f"Seu código de acesso é: {pretty}\n\n"
            "Digite ele na tela do app pra entrar (vale por "
            f"{_SIGNUP_CODE_TTL_MIN} minutos, uso único).\n\n"
            f"Ou toque no link: {link}\n\n"
            "Se não foi você que pediu, é só ignorar este e-mail.\n\n"
            "— Ritmind"
        )

        body_html = (
            "<p>Bem-vindo ao <b>Ritmind</b>!</p>"
            "<p>Seu código de acesso é:</p>"
            f'<p style="font-size:28px;font-weight:800;letter-spacing:4px;'
            f'font-family:monospace;color:#0FB499">{pretty}</p>'
            "<p>Digite ele na tela do app pra entrar — vale por "
            f"{_SIGNUP_CODE_TTL_MIN} minutos, uso único.</p>"
            f'<p style="color:#8A8B9E;font-size:12px">Ou toque no link:<br>'
            f'<a href="{link}">{link}</a></p>'
            '<p style="color:#8A8B9E;font-size:12px">Se não foi você que pediu, '
            "ignore este e-mail.</p>"
        )

        EmailSender.send(email, subject, body_text, body_html)

    @staticmethod
    def _skeleton(slug: str, email: str) -> dict:
        """Perfil mínimo válido pra sustentar a sessão entre o cadastro e o fim
        do wizard. Os placeholders (idade/peso/altura 0, objetivo vazio) são
        sobrescritos pelo `AppOnboardingService.complete`. `onboarding_complete`
        False é o que manda o app pro wizard."""

        name = email.split("@")[0][:40] or "corredor"

        return {
            "id": slug,
            "name": name,
            "age": 0,
            "weight": 0.0,
            "height": 0.0,
            "phone": "",
            "goal": "",
            "weekly_training_days": 0,
            "preferred_running_days": [],
            "strength_training_days": [],
            "injuries": [],
            "channel": "app",
            "telegram_id": None,
            "email": email,
            "notifications": True,
            "timezone": "America/Sao_Paulo",
            "language": "pt-BR",
            "onboarding_complete": False,
        }

    @staticmethod
    def _unique_slug(email: str) -> str:

        base = email.split("@")[0]

        normalized = unicodedata.normalize("NFKD", base.lower())

        slug = "".join(c for c in normalized if c.isalnum()) or "corredor"

        repo = RunnerProfileRepository()

        existing = set(repo.list_all())

        if slug not in existing:

            return slug

        suffix = 2

        while f"{slug}{suffix}" in existing:

            suffix += 1

        return f"{slug}{suffix}"
