"""Histórico de 'evitou o estímulo' por atleta e por família de treino de
qualidade (SPEED/TEMPO) — pro detector proativo de aversão enxergar o PADRÃO
(ex.: 3 dos últimos 4 tiros rebaixados). Guarda também se já puxamos conversa
sobre aquela família, pra não repetir a cada treino; o flag zera quando volta
um bom treino (o padrão quebrou)."""

import json
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "stimulus_miss"
)

# janela guardada por família (o detector olha os últimos 4)
_MAX_RECORDS = 8


class StimulusMissRepository:

    def __init__(self):

        self.storage = _STORAGE

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return {}

    def _save(self, profile: str, data: dict) -> None:

        self._file(profile).write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )

    def _entry(self, data: dict, family: str) -> dict:

        return data.get(family) or {"records": [], "nudged": False}

    def record(
        self,
        profile: str,
        family: str,
        date_iso: str,
        avoided: bool,
    ) -> None:

        data = self._load(profile)

        entry = self._entry(data, family)

        entry["records"].append(
            {"date": date_iso, "avoided": bool(avoided)},
        )

        entry["records"] = entry["records"][-_MAX_RECORDS:]

        data[family] = entry

        self._save(profile, data)

    def recent_avoided(
        self,
        profile: str,
        family: str,
        window: int,
    ) -> list[bool]:
        """Os últimos `window` resultados (mais antigo -> mais novo) de
        'evitou' daquela família."""

        entry = self._entry(self._load(profile), family)

        records = entry["records"][-window:]

        return [bool(r.get("avoided")) for r in records]

    def is_nudged(self, profile: str, family: str) -> bool:

        return bool(
            self._entry(self._load(profile), family)["nudged"],
        )

    def set_nudged(
        self,
        profile: str,
        family: str,
        value: bool,
    ) -> None:

        data = self._load(profile)

        entry = self._entry(data, family)

        entry["nudged"] = bool(value)

        data[family] = entry

        self._save(profile, data)
