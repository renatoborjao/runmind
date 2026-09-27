"""Guarda a ANÁLISE que o coach fez de cada treino — storage/workout_analysis/
{profile}.json. Escrita no pós-treino (junto do feedback) e lida pela tela da
atividade no app ("ver a análise que o coach fez do treino").

Chave = activity_id (idempotente: reprocessar o mesmo treino sobrescreve). A
leitura casa por DATA + distância aproximada (não por id), porque a mesma corrida
chega com ids diferentes do Garmin e do Strava e o feed faz dedup por data+
distância — a análise foi feita sobre uma fonte, o feed pode mostrar a outra.
Ver [[project_garmin_strava_dedup]]."""

import json
from datetime import UTC, datetime
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "workout_analysis"
)

# teto de análises guardadas por atleta (poda as mais antigas por data) — cobre
# meses de treino sem crescer sem limite
_MAX_ENTRIES = 300

# mesma tolerância de distância do dedup do feed (build_feed): a corrida do dia
# casa mesmo com pequena diferença entre fontes
_KM_TOLERANCE = 0.6


class WorkoutAnalysisRepository:

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

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (OSError, json.JSONDecodeError):

            return {}

    def record(
        self,
        profile: str,
        activity_id: int,
        date: str,
        distance_km: float,
        analysis: str,
        workout_type: str | None = None,
    ) -> None:
        """Grava/atualiza a análise de uma atividade. Idempotente (regravar o
        mesmo treino sobrescreve)."""

        data = self._load(profile)

        data[str(activity_id)] = {
            "date": date,
            "distance_km": round(distance_km, 2),
            "workout_type": workout_type,
            "analysis": analysis,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # poda por data: mantém as _MAX_ENTRIES mais recentes
        if len(data) > _MAX_ENTRIES:

            ordered = sorted(
                data.items(),
                key=lambda kv: kv[1].get("date", ""),
                reverse=True,
            )

            data = dict(ordered[:_MAX_ENTRIES])

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

    def find(
        self,
        profile: str,
        date: str,
        distance_km: float | None = None,
    ) -> dict | None:
        """Análise de um treino, casada pela DATA (e distância, quando informada:
        preferimos a de distância mais próxima dentro da tolerância). Em empate,
        a mais recente. None quando não há análise pra aquele dia."""

        candidates = [
            entry
            for entry in self._load(profile).values()
            if entry.get("date") == date
        ]

        if not candidates:

            return None

        if distance_km is not None:

            near = [
                entry
                for entry in candidates
                if abs((entry.get("distance_km") or 0) - distance_km)
                <= _KM_TOLERANCE
            ]

            if near:

                # sort estável em 2 passos: 1º por recência (mais nova primeiro),
                # 2º pela distância mais próxima — assim, em empate de distância,
                # fica a análise mais recente.
                near.sort(key=lambda e: e.get("created_at") or "", reverse=True)

                near.sort(
                    key=lambda e: abs((e.get("distance_km") or 0) - distance_km)
                )

                return near[0]

        # sem distância (ou nenhuma casou na tolerância): a mais recente do dia
        candidates.sort(key=lambda e: e.get("created_at") or "", reverse=True)

        return candidates[0]

    def annotate(
        self,
        profile: str,
        date: str,
        distance_km: float | None,
        **fields,
    ) -> bool:
        """Grava campos extras NA análise daquele treino (mesmo casamento do
        `find`) — ex.: a frase curta do card "Coach diz". Reanalisar o treino
        (`record`) reescreve a entrada e descarta o extra, que se regenera.
        False quando não há análise pro dia."""

        entry = self.find(profile, date, distance_km)

        if entry is None:

            return False

        data = self._load(profile)

        for key, value in data.items():

            if value == entry:

                data[key] = {**value, **fields}

                with open(self._file(profile), "w", encoding="utf-8") as f:

                    json.dump(data, f, ensure_ascii=False, indent=2)

                return True

        return False
