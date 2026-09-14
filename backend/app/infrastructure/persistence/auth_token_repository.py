from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from app.core.clock import now_local


class AuthTokenRepository:
    """Guarda os magic links pendentes: token opaco -> {perfil, vencimento,
    usado}. Uso ÚNICO e validade curta — a segurança do login mora aqui (o
    cookie de sessão vem só DEPOIS de consumir um token válido).

    Um arquivo só (storage/auth/magic_tokens.json). Tokens vencidos/usados são
    varridos na leitura (higiene retroativa, sem migração)."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "auth"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

        self.file = self.storage / "magic_tokens.json"

    def _load(self) -> dict:

        if not self.file.exists():

            return {}

        try:

            with open(self.file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            return {}

    def _save(self, data: dict) -> None:

        with open(self.file, "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

    def issue(self, profile: str, ttl_minutes: int) -> str:
        """Cria um token novo pro perfil e devolve ele. Varre os caducos de
        quebra pra o arquivo não crescer à toa."""

        now = now_local()

        data = self._load()

        # higiene: descarta vencidos/usados
        data = {
            tok: rec
            for tok, rec in data.items()
            if not rec.get("used")
            and self._still_valid(rec, now)
        }

        token = secrets.token_urlsafe(32)

        data[token] = {
            "profile": profile,
            "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
            "used": False,
        }

        self._save(data)

        return token

    def issue_code(self, profile: str, ttl_minutes: int, length: int = 6) -> str:
        """Como `issue`, mas gera um CÓDIGO curto e digitável (só letras/dígitos
        sem ambiguidade — nada de 0/O/1/I/L) pro atleta digitar DENTRO do app.
        Resolve o iOS: o magic link abre no navegador do Telegram/num contexto
        diferente do PWA instalado, então o cookie não vale onde ele usa o app;
        o código digitado na própria tela loga no contexto certo. Guardado igual
        ao token (mesma consumação de uso único)."""

        now = now_local()

        data = self._load()

        data = {
            tok: rec
            for tok, rec in data.items()
            if not rec.get("used") and self._still_valid(rec, now)
        }

        # gera um código único entre os pendentes (colisão é rara, mas garante)
        code = self._new_code(length)

        while code in data:

            code = self._new_code(length)

        data[code] = {
            "profile": profile,
            "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
            "used": False,
        }

        self._save(data)

        return code

    # alfabeto sem caracteres ambíguos (0/O, 1/I/L) — fácil de ler e digitar
    _CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    @classmethod
    def _new_code(cls, length: int) -> str:

        return "".join(secrets.choice(cls._CODE_ALPHABET) for _ in range(length))

    def consume(self, token: str) -> str | None:
        """Valida e QUEIMA o token (uso único). Devolve o perfil se válido;
        None se inexistente, já usado ou vencido."""

        if not token:

            return None

        data = self._load()

        rec = data.get(token)

        if not rec or rec.get("used"):

            return None

        if not self._still_valid(rec, now_local()):

            return None

        rec["used"] = True

        data[token] = rec

        self._save(data)

        return rec.get("profile")

    @staticmethod
    def _still_valid(rec: dict, now: datetime) -> bool:

        try:

            return datetime.fromisoformat(rec["expires_at"]) > now

        except (KeyError, ValueError, TypeError):

            return False
