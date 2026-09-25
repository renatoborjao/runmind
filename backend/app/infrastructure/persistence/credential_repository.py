"""Credenciais de acesso ao app, SEPARADAS do perfil (o perfil circula por
muito código — contexto do coach, debug, backup legível; a senha não).

storage/auth/credentials/{profile}.json
    {"password_hash": "...", "password_set_at": "...",
     "google_sub": "...", "google_email": "..."}
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

_SLUG = re.compile(r"^[a-z0-9_-]+$")


class CredentialRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3]
            / "storage"
            / "auth"
            / "credentials"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        if not _SLUG.match(profile or ""):

            raise ValueError("perfil inválido")

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError):

            return {}

    def _update(self, profile: str, fields: dict) -> None:

        data = self.load(profile)

        data.update(fields)

        file = self._file(profile)

        tmp = file.with_suffix(".tmp")

        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")

        tmp.replace(file)  # escrita atômica: nunca deixa credencial pela metade

    def password_hash(self, profile: str) -> str | None:

        return self.load(profile).get("password_hash")

    def set_password_hash(self, profile: str, password_hash: str) -> None:

        self._update(
            profile,
            {
                "password_hash": password_hash,
                "password_set_at": datetime.now(UTC).isoformat(),
            },
        )

    def google_sub(self, profile: str) -> str | None:

        return self.load(profile).get("google_sub")

    def link_google(self, profile: str, sub: str, email: str) -> None:

        self._update(profile, {"google_sub": sub, "google_email": email})

    def find_by_google_sub(self, sub: str) -> str | None:

        for file in self.storage.glob("*.json"):

            try:

                if json.loads(file.read_text(encoding="utf-8")).get("google_sub") == sub:

                    return file.stem

            except (OSError, json.JSONDecodeError):

                continue

        return None
