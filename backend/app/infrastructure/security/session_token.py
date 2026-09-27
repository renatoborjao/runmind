from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import get_settings

# Piso de desenvolvimento: só vale quando auth_session_secret está vazio (dev).
# Em produção o segredo TEM que vir do .env — o SessionToken recusa assinar com
# este piso quando app_env == "production".
_DEV_SECRET = "ritmind-dev-session-secret-troque-em-producao"


def _b64e(raw: bytes) -> str:

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:

    pad = "=" * (-len(text) % 4)

    return base64.urlsafe_b64decode(text + pad)


class SessionToken:
    """Cookie de sessão sem estado (stateless), assinado com HMAC-SHA256.

    Formato: base64url(payload_json).base64url(assinatura). O payload guarda o
    perfil (sub) e o vencimento (exp, epoch). Ninguém forja sem o segredo, e o
    conteúdo é legível mas não sigiloso (não guardamos nada sensível nele)."""

    @staticmethod
    def _secret() -> bytes:

        settings = get_settings()

        secret = settings.auth_session_secret.strip()

        if not secret:

            if settings.app_env == "production":

                raise RuntimeError(
                    "auth_session_secret vazio em produção — defina no .env"
                )

            secret = _DEV_SECRET

        return secret.encode("utf-8")

    @staticmethod
    def _sign(payload_b64: str) -> str:

        mac = hmac.new(
            SessionToken._secret(),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()

        return _b64e(mac)

    @staticmethod
    def issue(
        profile: str,
        ttl_days: int | None = None,
        purpose: str | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Emite um token pro perfil, válido por `ttl_days` (ou `ttl_seconds`).

        Com `purpose` (ex.: "strava_connect") vira um token de USO RESTRITO: só
        `verify(token, purpose=...)` com a mesma finalidade aceita, e nunca vale
        como sessão. É o que deixa mandar a identidade do atleta num `state` de
        OAuth (que passa por URL de terceiro) sem vazar um cookie de sessão."""

        if ttl_seconds is None:

            days = (
                ttl_days
                if ttl_days is not None
                else get_settings().auth_session_ttl_days
            )

            ttl_seconds = days * 86400

        payload = {
            "sub": profile,
            "exp": int(time.time()) + ttl_seconds,
        }

        if purpose:

            payload["aud"] = purpose

        payload_b64 = _b64e(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )

        return f"{payload_b64}.{SessionToken._sign(payload_b64)}"

    @staticmethod
    def verify(token: str | None, purpose: str | None = None) -> str | None:
        """Devolve o perfil se o token é válido (assinatura ok, não vencido e da
        MESMA finalidade — sessão = sem `purpose`); None caso contrário. Nunca
        levanta."""

        if not token or "." not in token:

            return None

        try:

            payload_b64, signature = token.rsplit(".", 1)

            expected = SessionToken._sign(payload_b64)

            # comparação em tempo constante (não vaza por timing)
            if not hmac.compare_digest(signature, expected):

                return None

            payload = json.loads(_b64d(payload_b64))

            if int(payload.get("exp", 0)) < int(time.time()):

                return None

            if payload.get("aud") != purpose:

                return None

            sub = payload.get("sub")

            return sub if isinstance(sub, str) and sub else None

        except Exception:

            return None

    @staticmethod
    def expires_at(token: str | None) -> int | None:
        """Vencimento (epoch) de uma SESSÃO válida; None se não é uma."""

        if not SessionToken.verify(token):

            return None

        try:

            return int(json.loads(_b64d(token.rsplit(".", 1)[0]))["exp"])

        except Exception:

            return None
