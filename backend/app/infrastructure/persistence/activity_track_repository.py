"""Acervo do TRAÇADO das atividades (mapa + parciais) — SEPARADO do arquivo de
treino/análise. Guarda o que o app precisa pra desenhar o percurso e os splits
de uma corrida sincronizada (Strava/Garmin), sem inchar o registro enxuto que a
análise/ACWR usa. Um arquivo por atleta: storage/activity_tracks/{profile}.json,
mapeando id_da_atividade -> {points, splits}. Best-effort: nada aqui é crítico."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.clock import now_local
from app.infrastructure.integrations.strava.polyline import decode_polyline


def _fmt_pace(sec_per_km: float) -> str:

    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def track_from_strava_raw(raw: dict) -> dict | None:
    """Extrai {points, splits} do JSON detalhado do Strava. points do
    summary_polyline; splits do splits_metric (por km). None se não há traçado."""

    if not raw:

        return None

    poly = ((raw.get("map") or {}).get("polyline")
            or (raw.get("map") or {}).get("summary_polyline"))

    points = [{"lat": lat, "lon": lon} for lat, lon in decode_polyline(poly or "")]

    splits = []

    for s in raw.get("splits_metric") or []:

        dist = float(s.get("distance") or 0)
        sec = float(s.get("moving_time") or s.get("elapsed_time") or 0)

        if dist <= 0 or sec <= 0:

            continue

        partial = round(dist / 1000, 2) if dist < 950 else None

        splits.append({
            "km": None if partial else int(s.get("split") or (len(splits) + 1)),
            "sec": round(sec, 1),
            "pace": _fmt_pace(sec / (dist / 1000)),
            "partial_km": partial,
        })

    if not points and not splits:

        return None

    return {"points": points, "splits": splits}


class ActivityTrackRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "activity_tracks"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict:

        file = self._file(profile)

        if not file.exists():

            return {}

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            return {}

    def has(self, profile: str, activity_id) -> bool:

        return str(activity_id) in self.load(profile)

    def get(self, profile: str, activity_id) -> dict | None:

        return self.load(profile).get(str(activity_id))

    def save(self, profile: str, activity_id, track: dict) -> None:

        data = self.load(profile)

        data[str(activity_id)] = {**track, "saved_at": now_local().isoformat()}

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)
