"""Login por e-mail + senha — o acesso que NÃO depende de canal nenhum
(Telegram, e-mail). Atleta que nasceu no app volta sempre por aqui (ou Google).

Segurança:
- senha em scrypt, fora do perfil (CredentialRepository);
- resposta de erro única pra e-mail inexistente ou senha errada, e mesmo custo
  de CPU nos dois casos (não dá pra descobrir quem tem conta);
- trava de força bruta: muitas falhas seguidas no mesmo e-mail travam por um
  tempo (em memória — o app roda num processo só).
"""

from __future__ import annotations

import time

from app.infrastructure.persistence.credential_repository import (
    CredentialRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.security.password_hasher import (
    DUMMY_HASH,
    hash_password,
    verify_password,
)

MIN_PASSWORD_LENGTH = 8

MAX_PASSWORD_LENGTH = 200

MAX_FAILURES = 5

LOCK_SECONDS = 15 * 60


class PasswordError(ValueError):
    """Senha nova fora da regra, ou senha atual não confere."""


class LoginLocked(Exception):
    """Muitas tentativas erradas nesse e-mail — espera `retry_after` segundos."""

    def __init__(self, retry_after: int):

        super().__init__("muitas tentativas")

        self.retry_after = retry_after


# e-mail -> [instantes das falhas recentes]
_failures: dict[str, list[float]] = {}


def _recent_failures(key: str, now: float) -> list[float]:

    recent = [t for t in _failures.get(key, []) if now - t < LOCK_SECONDS]

    _failures[key] = recent

    return recent


def validate_new_password(password: str) -> None:

    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:

        raise PasswordError(
            f"a senha precisa de pelo menos {MIN_PASSWORD_LENGTH} caracteres"
        )

    if len(password) > MAX_PASSWORD_LENGTH:

        raise PasswordError("senha longa demais")


class PasswordAuthService:

    @staticmethod
    def login(email: str, password: str) -> str | None:
        """Perfil do atleta se e-mail+senha conferem; None caso contrário.
        Levanta LoginLocked quando o e-mail está travado por tentativas."""

        key = (email or "").strip().lower()

        now = time.time()

        recent = _recent_failures(key, now)

        if len(recent) >= MAX_FAILURES:

            raise LoginLocked(int(LOCK_SECONDS - (now - recent[0])) + 1)

        profile = (
            RunnerProfileRepository().find_by_email(key)
            if key and "@" in key
            else None
        )

        stored = CredentialRepository().password_hash(profile) if profile else None

        # sempre roda o scrypt (com um hash falso se não há conta/senha)
        ok = verify_password(password or "", stored or DUMMY_HASH) and bool(stored)

        if not ok:

            recent.append(now)

            return None

        _failures.pop(key, None)

        return profile

    @staticmethod
    def has_password(profile: str) -> bool:

        return bool(CredentialRepository().password_hash(profile))

    @staticmethod
    def set_password(
        profile: str,
        new_password: str,
        current_password: str | None = None,
    ) -> None:
        """Cria ou troca a senha. Trocar exige a atual; criar a primeira não
        (o atleta já está logado — por Telegram, Google ou link)."""

        validate_new_password(new_password)

        repo = CredentialRepository()

        stored = repo.password_hash(profile)

        if stored and not verify_password(current_password or "", stored):

            raise PasswordError("a senha atual não confere")

        repo.set_password_hash(profile, hash_password(new_password))

    @staticmethod
    def reset_password(profile: str, new_password: str) -> None:
        """Define a senha SEM pedir a atual — só pra quem provou ser o dono
        por outro caminho agora (link de recuperação por e-mail)."""

        validate_new_password(new_password)

        CredentialRepository().set_password_hash(profile, hash_password(new_password))
