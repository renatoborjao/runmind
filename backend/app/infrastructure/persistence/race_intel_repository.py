"""Cache dos dossiês de prova (pesquisa na web), COMPARTILHADO entre atletas:
storage/race_intel/{nome-normalizado}_{data}.json. Ver RaceIntelService."""

from __future__ import annotations

import json
import re
from pathlib import Path

_KEY = re.compile(r"^[a-z0-9-]+_\d{4}-\d{2}-\d{2}$")


class RaceIntelRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "race_intel"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, key: str) -> Path | None:

        return self.storage / f"{key}.json" if _KEY.match(key or "") else None

    def load(self, key: str) -> dict | None:

        file = self._file(key)

        if file is None or not file.exists():

            return None

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError):

            return None

    def save(self, key: str, data: dict) -> None:

        file = self._file(key)

        if file is None:

            return

        tmp = file.with_suffix(".tmp")

        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        tmp.replace(file)
