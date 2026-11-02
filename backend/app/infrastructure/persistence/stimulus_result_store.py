"""Veredito de estímulo de tiro POR ATIVIDADE — storage/stimulus_results/
{profile}.json. Guardado no pós-treino (quando há splits do Garmin), lido em
LOTE pelo report de aderência (o arquivo reduzido não tem splits pra recalcular
depois). Mapa activity_id -> {date, on_target, total, verdict}. Ver
[[stimulus_result]]."""

import json
from pathlib import Path

from app.infrastructure.persistence.permanent_archive import PermanentArchive

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "stimulus_results"
)

# teto de atividades guardadas (poda as mais antigas por data) — cobre bem mais
# que a janela de 8 semanas do report, sem crescer sem limite
_MAX_ENTRIES = 200


class StimulusResultStore:

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
        """Mapa activity_id (int) -> resumo. Chaves JSON são string; converte."""

        return {int(k): v for k, v in self._load(profile).items()}

    def record(
        self, profile: str, activity_id: int, date: str, result: dict
    ) -> None:
        """Grava/atualiza o veredito de uma atividade. Idempotente (regravar o
        mesmo treino sobrescreve com o mesmo valor)."""

        data = self._load(profile)

        data[str(activity_id)] = {"date": date, **result}

        # a janela mantém as _MAX_ENTRIES mais recentes; o resto vai pro arquivo permanente
        data = PermanentArchive.trim_dict(_STORAGE, "stimulus_results", profile, data, _MAX_ENTRIES)

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)
