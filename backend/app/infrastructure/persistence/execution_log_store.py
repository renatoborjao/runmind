"""Execução bloco-a-bloco POR ATIVIDADE — storage/execution_log/{profile}.json.
Gravada no pós-treino (quando há voltas do relógio pareadas com os passos
prescritos) e lida pelo PLANEJADO × EXECUTADO do dossiê — o arquivo reduzido
não guarda voltas, então não dá pra recalcular depois. Mapa activity_id ->
{date, km, blocks, missing}. Ver [[execution_log]]."""

import json
from pathlib import Path

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

        data[str(activity_id)] = {"date": day, "km": round(km, 2), **entry}

        if len(data) > _MAX_ENTRIES:

            ordered = sorted(
                data.items(), key=lambda kv: kv[1].get("date", ""), reverse=True,
            )

            data = dict(ordered[:_MAX_ENTRIES])

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)
