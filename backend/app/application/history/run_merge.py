"""Lista unificada de corridas pro DISPLAY (km/jornada/evolução): histórico
arquivado (Strava/Garmin) + corridas gravadas no GPS do app, com dedup por
CORRIDA (mesma data + distância ~igual = a mesma corrida vinda de outra fonte).

IMPORTANTE — escopo: isto é SÓ pros contadores visuais (EvolutionBuilder). NÃO
entra no pipeline de ANÁLISE/ACWR — o invariante do Renato é que a análise do
treino segue no Garmin pra quem tem conectado ([[project_analise_garmin_padrao]]).
App-GPS é "só mais uma base" ([[project_app_atleta]] — conceito app-GPS)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    s = (sport or "").lower()

    return any(h in s for h in _RUN_HINT)


def _run_date(r: dict) -> date | None:
    """Data de uma corrida gravada no app (started_at; cai no saved_at)."""

    for key in ("started_at", "saved_at"):

        v = r.get(key)

        if v:

            try:

                return date.fromisoformat(str(v)[:10])

            except ValueError:

                continue

    return None


def merged_runs(profile: str) -> list:
    """Corridas do atleta pro display: arquivadas (corridas de verdade) + as do
    GPS do app que NÃO são a mesma corrida já arquivada (dedup por data +
    distância ~igual, tolerância 0,6 km). Devolve objetos com `.start_date`
    (datetime) e `.distance` (metros) — compatível com group_by_week/_journey."""

    archive = [
        a
        for a in ActivityArchiveRepository().load_activities(profile)
        if _is_run(a.sport)
    ]

    out: list = list(archive)

    try:

        recorded = RecordedRunRepository().load(profile) or []

    except Exception as e:

        print(f"[run_merge] recorded_runs falhou p/ '{profile}': {e}")

        recorded = []

    for r in recorded:

        d = _run_date(r)

        if d is None:

            continue

        dist_m = float(r.get("distance_m") or 0.0)
        km = dist_m / 1000

        # mesma corrida já arquivada (outra base)? não conta de novo
        dup = any(
            a.start_date.date() == d and abs(a.distance / 1000 - km) < 0.6
            for a in archive
        )

        if dup:

            continue

        out.append(
            SimpleNamespace(
                start_date=datetime(d.year, d.month, d.day),
                distance=dist_m,
                source="app",
            )
        )

    return out
