"""Execução bloco-a-bloco POR ATIVIDADE — storage/execution_log/{profile}.json.
Gravada no pós-treino (quando há voltas do relógio pareadas com os passos
prescritos) e lida pelo PLANEJADO × EXECUTADO do dossiê — o arquivo reduzido
não guarda voltas, então não dá pra recalcular depois. Mapa activity_id ->
{date, km, blocks, missing}. Ver [[execution_log]]."""

import json
from pathlib import Path

from app.infrastructure.persistence.permanent_archive import PermanentArchive

_STORAGE = Path(__file__).resolve().parents[3] / "storage" / "execution_log"

# teto de atividades guardadas (poda as mais antigas por data) — cobre com
# folga a janela do dossiê sem crescer sem limite
_MAX_ENTRIES = 200


class ExecutionLogStore:

    def __init__(self):

        _STORAGE.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (OSError, json.JSONDecodeError):

            return {}

    def all(self, profile: str) -> dict[int, dict]:

        return {int(k): v for k, v in self._load(profile).items()}

    def record(
        self, profile: str, activity_id: int, day: str, km: float, entry: dict,
    ) -> None:
        """Grava/atualiza a execução de uma atividade. Idempotente (reanalisar
        o mesmo treino sobrescreve)."""

        data = self._load(profile)

        new = {"date": day, "km": round(km, 2), **entry}

        previous = data.get(str(activity_id))

        # reanalisar o mesmo treino sobrescreve: a leitura anterior fica guardada
        if previous and previous != new:

            PermanentArchive.append(
                _STORAGE, "execution_log", profile,
                [{"key": str(activity_id), "value": previous}], "substituída (reanálise)",
            )

        data[str(activity_id)] = new

        data = PermanentArchive.trim_dict(_STORAGE, "execution_log", profile, data, _MAX_ENTRIES)

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)
