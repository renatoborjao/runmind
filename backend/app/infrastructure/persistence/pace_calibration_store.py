"""Amostras do ERRO de previsão de pace do coach: por bloco de QUALIDADE (tiro),
o quanto o atleta correu mais devagar/rápido que o ritmo PRESCRITO. É a matéria-
prima da auto-calibração — o coach medir o próprio erro e ajustar o alvo pro que
o atleta SUSTENTA (regra de ouro: ritmo que não se sustenta não treina, arrisca
lesão). Rolling das últimas amostras + dedup por atividade. Ver
[[project_modelo_pace_vdot]] e [[pace_calibration_analyzer]]."""

import json
from pathlib import Path

# quantas amostras recentes guardar (janela rolante — o atleta evolui, o erro
# de meses atrás não descreve o presente)
_MAX_SAMPLES = 24

# quantos ids de atividade lembrar (dedup de reprocessamento)
_MAX_IDS = 60


class PaceCalibrationStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "pace_calibration"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {"processed_ids": [], "samples": []}

        with open(file, encoding="utf-8") as f:

            return json.load(f)

    def processed_ids(self, profile: str) -> set[int]:

        return set(self._load(profile).get("processed_ids", []))

    def deltas(self, profile: str) -> list[float]:
        """Erros de pace recentes (s/km): + = correu MAIS DEVAGAR que o alvo."""

        return [s["delta"] for s in self._load(profile).get("samples", [])]

    def record(
        self, profile: str, activity_id: int, deltas: list[float]
    ) -> bool:
        """Grava as amostras desta atividade (uma por bloco de qualidade). Pula
        se a atividade já foi processada (dedup). Retorna se gravou."""

        data = self._load(profile)

        if activity_id in set(data.get("processed_ids", [])):

            return False

        if not deltas:

            return False

        samples = data.get("samples", [])

        samples.extend({"id": activity_id, "delta": round(d, 1)} for d in deltas)

        data["samples"] = samples[-_MAX_SAMPLES:]

        ids = data.get("processed_ids", [])

        ids.append(activity_id)

        data["processed_ids"] = ids[-_MAX_IDS:]

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

        return True
