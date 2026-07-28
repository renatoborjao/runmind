"""Backfill do contador de CARGA DO CORPO — atividades NÃO-corrida
(musculação/natação/Hyrox/bike) do Garmin dos últimos ~35 dias. Roda UMA vez
pra o ACWR do corpo já nascer com o estresse real. NÃO analisa nada — só
popula o contador (a leitura/plano de corrida seguem só corrida). Ver
[[project_analise_corpo_garmin]].

Uso:
  python cross_training_seed.py <profile>   # um atleta
  python cross_training_seed.py             # todos os conectados + análise on
"""

import sys

from app.application.garmin.garmin_activity_poller import GarminActivityPoller
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


def seed(profile: str) -> None:

    if not GarminClient.is_connected(profile):

        print(f"  {profile}: Garmin nao conectado -- pulado")

        return

    print(f"  {profile}: puxando cross-training...", flush=True)

    stored = GarminActivityPoller.seed_cross_training(profile)

    print(f"  {profile}: {stored} atividades de cross-training gravadas")


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
