"""Backfill da TEMPERATURA (°C) nos treinos do arquivo, a partir do Strava.

O Strava traz `average_temp` por treino (gravado pelo dispositivo) — histórico
e futuro, de graça. Antes o mapper não guardava esse campo; agora guarda, mas os
registros ANTIGOS do arquivo não têm. Este script re-busca as últimas N
atividades do Strava (já mapeadas com a temperatura) e dá upsert no arquivo —
assim a normalização de calor da eficiência aeróbica passa a valer no histórico,
sem esperar novas corridas. No read-time, o dedup transfere a temperatura da
cópia Strava pra cópia Garmin (atleta analisado via relógio). Best-effort.

Uso:  python seed_air_temp.py <profile> [n]
Ex.:  python seed_air_temp.py renato2 60
"""

import asyncio
import sys

from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)


async def main(profile: str, n: int) -> None:

    try:

        activities = await StravaClient(profile).get_last_activities(limit=n)

    except Exception as e:

        print(f"'{profile}': falhou ao buscar Strava ({e})")

        return

    with_temp = [a for a in activities if a.air_temp_c is not None]

    if not with_temp:

        print(f"'{profile}': nenhuma das {len(activities)} atividades tem temp.")

        return

    ActivityArchiveRepository().upsert_many(profile, with_temp)

    for a in with_temp:

        # nome pode ter emoji; o console cp1252 (Windows) quebraria no print
        name = a.name[:30].encode("ascii", "replace").decode("ascii")

        print(f"{a.id} {a.start_date.date()} {name}: {a.air_temp_c}C")

    print(
        f"\nOK — {len(with_temp)} de {len(activities)} treino(s) do Strava "
        f"stampados com temperatura."
    )


if __name__ == "__main__":

    profile = sys.argv[1] if len(sys.argv) > 1 else "renato2"

    n = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    asyncio.run(main(profile, n))
