"""Ajustes SOCIAIS do atleta — separado do perfil de treino: modo do perfil
(público × com solicitação) e bio curta. Um arquivo por atleta:
storage/social_profiles/{profile}.json. Best-effort, nada aqui é crítico."""

from __future__ import annotations

import json
from pathlib import Path

# público: qualquer atleta segue na hora e vê as atividades.
# privado: seguir precisa de aprovação; só seguidores aprovados veem atividades.
PUBLIC = "public"
PRIVATE = "private"
_DEFAULT = {"privacy": PUBLIC, "bio": ""}


class SocialProfileRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "social_profiles"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def get(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return dict(_DEFAULT)

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

            return {**_DEFAULT, **data}

        except (json.JSONDecodeError, OSError):

            return dict(_DEFAULT)

    def is_public(self, profile: str) -> bool:

        return self.get(profile).get("privacy", PUBLIC) == PUBLIC

    def set(self, profile: str, *, privacy: str | None = None, bio: str | None = None) -> dict:

        data = self.get(profile)

        if privacy in (PUBLIC, PRIVATE):

            data["privacy"] = privacy

        if bio is not None:

            data["bio"] = bio.strip()[:280]

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

        return data
