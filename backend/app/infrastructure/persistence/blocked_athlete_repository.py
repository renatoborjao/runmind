"""Atletas DESLIGADOS da base (ex.: pararam de usar o app e o Renato não quer
mais gastar com eles). Um arquivo só (storage/auth/blocked_athletes.json),
chaveado pelo slug antigo:

    "joaosoares": {"name": "...", "email": "...", "telegram_id": "...",
                   "phone": "...", "strava_athlete_id": 123,
                   "blocked_at": "...", "reason": "...",
                   "last_notice_at": "..."|null}

Bloqueado não volta sozinho: mensagem de Telegram/WhatsApp não abre cadastro
(sem IA, um aviso fixo de vez em quando), sessão antiga do app cai em 401.
Só volta por CONVITE — o cadastro com convite tira o e-mail daqui."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from app.core.clock import now_local

_STORAGE = Path(__file__).resolve().parents[3] / "storage" / "auth"

# aviso fixo pro bloqueado que escreve: no máximo um a cada N dias
NOTICE_EVERY_DAYS = 30


def _norm_phone(value) -> str:

    return "".join(c for c in str(value or "") if c.isdigit())


class BlockedAthleteRepository:

    def __init__(self):

        self.file = _STORAGE / "blocked_athletes.json"

    def _load(self) -> dict:

        if not self.file.exists():

            return {}

        try:

            with open(self.file, encoding="utf-8") as f:

                data = json.load(f)

            return data if isinstance(data, dict) else {}

        except (json.JSONDecodeError, OSError):

            return {}

    def _save(self, data: dict) -> None:

        self.file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.file, "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

    def block(self, slug: str, profile: dict, reason: str = "") -> dict:
        """Grava o bloqueio a partir do perfil (dict) do atleta desligado."""

        data = self._load()

        entry = {
            "name": profile.get("name") or slug,
            "email": (profile.get("email") or "").strip().lower(),
            "telegram_id": str(profile.get("telegram_id") or ""),
            "phone": _norm_phone(profile.get("phone")),
            "strava_athlete_id": profile.get("strava_athlete_id"),
            "blocked_at": now_local().isoformat(),
            "reason": reason,
            "last_notice_at": None,
        }

        data[slug] = entry

        self._save(data)

        return entry

    def list(self) -> dict:

        return self._load()

    def is_slug_blocked(self, slug: str | None) -> bool:

        return bool(slug) and slug in self._load()

    def find_by_address(self, channel: str, address: str) -> str | None:
        """Slug bloqueado dono desse endereço (telegram_id ou telefone)."""

        if not address:

            return None

        for slug, entry in self._load().items():

            if channel == "telegram":

                if entry.get("telegram_id") and entry["telegram_id"] == str(address):

                    return slug

            elif entry.get("phone") and entry["phone"] == _norm_phone(address):

                return slug

        return None

    def should_notify(self, slug: str) -> bool:
        """True (e marca) se já passou o intervalo desde o último aviso."""

        data = self._load()

        entry = data.get(slug)

        if entry is None:

            return False

        last = entry.get("last_notice_at")

        now = now_local()

        if last:

            try:

                if now - datetime.fromisoformat(last) < timedelta(days=NOTICE_EVERY_DAYS):

                    return False

            except ValueError:

                pass

        entry["last_notice_at"] = now.isoformat()

        self._save(data)

        return True

    def unblock(self, slug: str) -> bool:

        data = self._load()

        if slug not in data:

            return False

        del data[slug]

        self._save(data)

        return True

    def unblock_email(self, email: str) -> list[str]:
        """Convite aceito: tira todo bloqueio com esse e-mail. Devolve os slugs."""

        email = (email or "").strip().lower()

        if not email:

            return []

        data = self._load()

        gone = [s for s, e in data.items() if e.get("email") == email]

        if gone:

            for s in gone:

                del data[s]

            self._save(data)

        return gone
