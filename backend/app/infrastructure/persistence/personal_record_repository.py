"""Melhores marcas conhecidas por atleta — storage/records/{profile}.json.
Alimenta o PersonalRecordDetector: sem isso não dá pra saber se um treino
bateu recorde (precisa comparar contra o melhor JÁ VISTO, não o do histórico
inteiro recalculado, senão o mesmo treino dispararia comemoração de novo a
cada reprocessamento)."""

import json
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "records"
)


class PersonalRecordRepository:

    def __init__(self):

        self.storage = _STORAGE

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return {}

    def save(self, profile: str, data: dict) -> None:

        self._file(profile).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
