"""Backfill do histórico de saúde do Garmin (sono/HRV/stress/prontidão) — roda
UMA vez pra a série já nascer rica, sem esperar acumular dia a dia.

Uso:
  python garmin_health_seed.py <profile>   # um atleta
  python garmin_health_seed.py             # todos os conectados + análise on
"""

import sys

from app.application.garmin.garmin_health_poller import GarminHealthPoller
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


def seed(profile: str) -> None:

    if not GarminClient.is_connected(profile):

        print(f"  {profile}: Garmin não conectado — pulado")

        return

    print(f"  {profile}: puxando histórico...", flush=True)

    pulled = GarminHealthPoller.seed_history(profile)

    print(f"  {profile}: {pulled} dias gravados")


def main() -> None:

    if len(sys.argv) > 1:

        seed(sys.argv[1])

        return

    for profile in RunnerProfileRepository().list_all():

        if GarminClient.is_connected(profile) and GarminClient.analysis_enabled(
            profile
        ):

            seed(profile)


if __name__ == "__main__":

    main()
