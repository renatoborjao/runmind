"""One-off (2026-08-01): re-baseline do `total_km_accumulated` pra contar SÓ a
jornada COM o RunMind — km de corrida desde a ENTRADA de cada atleta, não o
histórico pré-RunMind que o Strava trazia no seed.

Decisão do Renato: o marco "passou de X km com o RunMind" tem que ser honesto;
pouco importa a quilometragem de Strava anterior, o que vale é o que o atleta
rodou USANDO o app — e não podemos perder o que já rodou com a gente.

Data de entrada = a MAIS ANTIGA entre (1º plano gerado, 1ª conversa retida) —
o histórico de planos é o sinal mais fiel do início da jornada (a conversa é
truncada em 200 turnos). Km = atividades de PÉ (corrida/caminhada, mesma regra
do detector) no Strava com data >= entrada.

Dry-run por padrão (só mostra). Rode com `--apply` pra gravar.

    cd ~/runmind/backend && .venv/bin/python rebaseline_runmind_km.py [--apply]
"""

import asyncio
import glob
import json
import os
import sys
from datetime import date

from app.application.history.weekly_buckets import activity_date
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)
from app.infrastructure.storage.token_store import TokenStore

_KM_MILESTONES = [100, 250, 500, 1000, 1500, 2000, 3000, 5000]


def _earliest_plan_week(profile: str) -> date | None:

    path = f"storage/plans/history/{profile}.json"

    if not os.path.exists(path):

        return None

    data = json.load(open(path, encoding="utf-8"))

    seq = data if isinstance(data, list) else (
        data.get("weeks") or data.get("history") or list(data.values())
    )

    weeks = [
        w["week_start"][:10]
        for w in seq
        if isinstance(w, dict) and w.get("week_start")
    ]

    return date.fromisoformat(min(weeks)) if weeks else None


def _first_conversation(profile: str) -> date | None:

    path = f"storage/conversations/{profile}.json"

    if not os.path.exists(path):

        return None

    data = json.load(open(path, encoding="utf-8"))

    if not isinstance(data, list) or not data:

        return None

    return date.fromisoformat(data[0]["timestamp"][:10])


def _join_date(profile: str) -> date | None:

    candidates = [
        d for d in (_earliest_plan_week(profile), _first_conversation(profile))
        if d is not None
    ]

    return min(candidates) if candidates else None


async def _runmind_km(profile: str, since: date) -> tuple[float, int] | None:
    """Km de PÉ no Strava desde a entrada (mesma regra de esporte do
    detector). None se o atleta não tem Strava conectado."""

    if TokenStore(profile).load() is None:

        return None

    activities = await StravaClient(profile).get_last_activities(limit=200)

    foot = [
        a for a in activities
        if is_foot_sport(a.sport) and activity_date(a) >= since
    ]

    total_km = sum(a.distance for a in foot) / 1000

    return round(total_km, 2), len(foot)


async def main(apply: bool) -> None:

    repo = PersonalRecordRepository()

    for path in sorted(glob.glob("storage/records/*.json")):

        profile = os.path.basename(path)[:-5]

        records = repo.load(profile)

        old_km = records.get("total_km_accumulated")

        old_ms = records.get("total_km_milestone")

        since = _join_date(profile)

        if since is None:

            print(f"  {profile}: sem data de entrada — PULADO")

            continue

        result = await _runmind_km(profile, since)

        if result is None:

            print(f"  {profile}: sem Strava conectado — PULADO")

            continue

        km, n = result

        crossed = [m for m in _KM_MILESTONES if m <= km]

        new_ms = max(crossed) if crossed else None

        print(
            f"  {profile}: entrada={since} | {n} treinos c/ RunMind | "
            f"acumulado {old_km} -> {km} km | marco {old_ms} -> {new_ms}"
        )

        if apply:

            records["total_km_accumulated"] = km

            if new_ms is not None:

                records["total_km_milestone"] = new_ms

            else:

                records.pop("total_km_milestone", None)

            # sem data: um marco já passado não pode re-aparecer num recap;
            # o próximo que o atleta cruzar AO VIVO é que ganha data.
            records.pop("total_km_milestone_date", None)

            repo.save(profile, records)

    print("\n" + ("APLICADO ✅" if apply else "DRY-RUN — rode com --apply pra gravar"))


if __name__ == "__main__":

    asyncio.run(main("--apply" in sys.argv))
