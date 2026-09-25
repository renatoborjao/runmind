"""Hash de senha com scrypt (biblioteca padrão do Python — nada novo pra
instalar). Formato autodescritivo, pra dar pra endurecer os parâmetros no futuro
sem invalidar as senhas antigas:

    scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_N = 2 ** 14

_R = 8

_P = 1

_DKLEN = 32


def _b64e(raw: bytes) -> str:

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:

    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:

    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_DKLEN,
        maxmem=128 * 1024 * 1024,
    )


def hash_password(password: str) -> str:

    salt = os.urandom(16)

    digest = _derive(password, salt, _N, _R, _P)

    return f"scrypt${_N}${_R}${_P}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """True se a senha bate com o hash guardado. Nunca levanta."""

    try:

        algo, n, r, p, salt, digest = (stored or "").split("$")

        if algo != "scrypt":

            return False

        candidate = _derive(password, _b64d(salt), int(n), int(r), int(p))

        return hmac.compare_digest(candidate, _b64d(digest))

    except Exception:

        return False


# hash de uma senha qualquer: quem não tem conta também "paga" o custo do
# scrypt no login — o tempo de resposta não entrega se o e-mail existe
DUMMY_HASH = hash_password(os.urandom(12).hex())
