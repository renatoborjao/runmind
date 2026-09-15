from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from app.core.clock import now_local


class InviteCodeRepository:
    """Códigos de convite pro auto-cadastro no app. Enquanto o acesso é fechado
    (público baixo, fase de teste), só entra quem tem um código gerado pelo
    Renato. Um arquivo só (storage/auth/invite_codes.json):

        "RIT-7K2M": {"label": "amigos", "max_uses": 5, "uses": 1,
                     "expires_at": "..."|null, "created_at": "..."}

    `max_uses=None` = ilimitado; `expires_at=None` = não expira. `validate` não
    muta nada (checa se dá pra usar); `consume` incrementa o uso (chamado só
    quando o cadastro cria o perfil de fato)."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "auth"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

        self.file = self.storage / "invite_codes.json"

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

    # alfabeto sem caracteres ambíguos (0/O, 1/I/L) — fácil de ler e digitar
    _ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    def issue(
        self,
        label: str = "",
        max_uses: int | None = None,
        ttl_days: int | None = None,
    ) -> str:
        """Cria um convite novo e devolve o código (ex.: "RIT-7K2M")."""

        data = self._load()

        code = self._new_code()

        while code in data:

            code = self._new_code()

        expires_at = None

        if ttl_days is not None:

            expires_at = (now_local() + timedelta(days=ttl_days)).isoformat()

        data[code] = {
            "label": label,
            "max_uses": max_uses,
            "uses": 0,
            "expires_at": expires_at,
            "created_at": now_local().isoformat(),
        }

        self._save(data)

        return code

    @classmethod
    def _new_code(cls) -> str:

        body = "".join(secrets.choice(cls._ALPHABET) for _ in range(4))

        return f"RIT-{body}"

    @staticmethod
    def normalize(code: str) -> str:
        """Aceita o que o atleta digitar: tira espaços, maiúsculas, garante o
        prefixo RIT- (deixa digitar só os 4 dígitos do miolo)."""

        raw = (code or "").strip().upper().replace(" ", "")

        if not raw:

            return ""

        if raw.startswith("RIT-"):

            return raw

        if raw.startswith("RIT"):

            return "RIT-" + raw[3:]

        return "RIT-" + raw

    def validate(self, code: str) -> bool:
        """Dá pra usar este código agora? (existe, não expirou, tem uso
        sobrando). Não muta nada."""

        rec = self._load().get(self.normalize(code))

        return self._usable(rec)

    def consume(self, code: str) -> bool:
        """Queima um uso do convite. Devolve True se consumiu; False se o código
        é inválido/expirado/esgotado (aí o cadastro não deve prosseguir)."""

        key = self.normalize(code)

        data = self._load()

        rec = data.get(key)

        if not self._usable(rec):

            return False

        rec["uses"] = int(rec.get("uses", 0)) + 1

        data[key] = rec

        self._save(data)

        return True

    @staticmethod
    def _usable(rec: dict | None) -> bool:

        if not rec:

            return False

        max_uses = rec.get("max_uses")

        if max_uses is not None and int(rec.get("uses", 0)) >= int(max_uses):

            return False

        expires_at = rec.get("expires_at")

        if expires_at:

            try:

                if datetime.fromisoformat(expires_at) <= now_local():

                    return False

            except (ValueError, TypeError):

                return False

        return True
