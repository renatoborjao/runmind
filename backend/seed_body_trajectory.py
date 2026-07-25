"""Backfill da trajetória do corpo: reconstrói o histórico de leituras semana a
semana a partir do Garmin+atividades que o atleta JÁ tem, pra a trajetória
("3ª leitura seguida assim" / "melhorou desde a última") ter profundidade já —
sem esperar acumular domingo a domingo.

Honesto porque a leitura de cada semana passada usa reference_date: carga E
recuperação olham só até aquela data (não contaminam com o corpo de hoje).

Uso:
  python seed_body_trajectory.py <profile>   # um atleta
  python seed_body_trajectory.py             # todos os atletas
"""

import sys
from datetime import datetime, time, timedelta

from app.application.coach.intelligence.body_reading_builder import (
    BodyReadingBuilder,
)
from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import active_timezone, today_local, use_athlete_timezone
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# quantas semanas pra trás reconstruir (o repo corta no cap de 26 de qualquer
# jeito). Cobre ~3 meses — sobra pra a trajetória ter contexto.
_WEEKS = 12


def _weekly_refs():
    """Domingos (mais antigo -> mais recente) do último domingo pra trás."""

    today = today_local()

    # domingo mais recente <= hoje (weekday: seg=0 .. dom=6)
    last_sunday = today - timedelta(days=(today.weekday() - 6) % 7)

    refs = [last_sunday - timedelta(days=7 * k) for k in range(_WEEKS)]

    refs.reverse()

    return refs


def seed(profile: str) -> None:

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    tz = active_timezone()

    snapshots = []

    for ref in _weekly_refs():

        reading = BodyReadingBuilder.build(profile, reference_date=ref)

        # sem recuperação naquela data (antes de o atleta ter o Garmin, ou
        # série magra): não dá pra reconstruir a leitura — pula
        if not reading.recovery.has_data:

            continue

        at = datetime.combine(ref, time(20, 0), tzinfo=tz)

        snapshots.append(BodyReadingService.snapshot_of(reading, at))

    repo = BodyReadingHistoryRepository()

    # reconstrói do zero (idempotente: rodar de novo não duplica)
    repo._save(profile, snapshots[-BodyReadingHistoryRepository._MAX:])

    if not snapshots:

        print(f"  {profile}: sem dado de corpo no período (nada a semear)")

        return

    states = " -> ".join(s.body_state for s in snapshots)

    print(f"  {profile}: {len(snapshots)} leitura(s): {states}")


def main() -> None:

    if len(sys.argv) > 1:

        seed(sys.argv[1])

        return

    for profile in RunnerProfileRepository().list_all():

        seed(profile)


if __name__ == "__main__":

    main()
