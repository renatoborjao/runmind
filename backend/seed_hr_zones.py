"""Backfill das ZONAS DE FC nos treinos recentes do Garmin.

As zonas (pra a carga de Edwards) só passam a ser calculadas nos treinos NOVOS.
Este script re-busca os últimos N treinos do Garmin (que recomputa as zonas do
stream) e atualiza o arquivo — assim a carga de Edwards já liga sem esperar ~4
semanas de acúmulo. Best-effort, pacing gentil com a API não-oficial.

Uso:  python seed_hr_zones.py <profile> [n]
Ex.:  python seed_hr_zones.py renato2 15
"""

import sys
import time

from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)


def main(profile: str, n: int) -> None:

    if not GarminClient.is_connected(profile):

        print(f"'{profile}' não está conectado ao Garmin.")

        return

    garmin = GarminClient.connect(profile)

    archive = ActivityArchiveRepository()

    done = 0

    for item in garmin.get_activities(0, n) or []:

        activity_id = item.get("activityId")

        if activity_id is None:

            continue

        try:

            activity = GarminActivitySource.fetch(profile, activity_id)

            if not is_foot_sport(activity.sport):

                continue

            archive.upsert_many(profile, [activity])

            zones = activity.hr_zone_minutes

            print(
                f"{activity_id} {activity.start_date.date()} "
                f"{activity.name[:30]}: "
                f"{'zonas ' + str(zones) if zones else 'sem zonas (sem stream/idade)'}"
            )

            done += 1

        except Exception as e:

            print(f"{activity_id}: falhou ({e})")

        time.sleep(1.2)

    print(f"\nOK — {done} treino(s) atualizados com zonas de FC.")


if __name__ == "__main__":

    profile = sys.argv[1] if len(sys.argv) > 1 else "renato2"

    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    main(profile, n)
