"""Teste ponta-a-ponta do push pro Garmin: monta 2 treinos de exemplo (um
longão contínuo com pace-alvo e um de tiros) e agenda no seu calendário do
Garmin Connect. Depois é só abrir o app/relógio e conferir se apareceram.

Pré-requisito: ter feito o login uma vez (python garmin_login.py <profile>).

Uso:  python garmin_push_test.py <profile> [YYYY-MM-DD]
Ex.:  python garmin_push_test.py renato2 2026-07-11
"""

import sys
from datetime import date, timedelta

from app.application.garmin.garmin_push import push_session
from app.domain.entities.planned_session import PlannedSession


def _samples() -> list[PlannedSession]:

    longao = PlannedSession(
        day="Saturday",
        workout_type="Longão",
        objective="Resistência aeróbica",
        planned_distance_km=12.2,
        planned_duration_minutes=None,
        target_pace_min="6:32",
        target_pace_max="7:08",
        purpose="resistência aeróbica",
        structure=(
            "Aquecimento: 2 km leve\n"
            "Principal: 12,2 km em ritmo confortável (6:32-7:08/km)\n"
            "Dica: mantenha constante, sem acelerar no fim"
        ),
    )

    tiros = PlannedSession(
        day="Tuesday",
        workout_type="Velocidade",
        objective="ritmo de prova",
        planned_distance_km=9.0,
        planned_duration_minutes=None,
        target_pace_min="4:45",
        target_pace_max="4:50",
        purpose="velocidade",
        structure=(
            "Aquecimento: 2 km leve + 3 educativos\n"
            "Série: 6x 800m no pace 4:45-4:50/km\n"
            "Recuperação: 400m de trote entre os tiros\n"
            "Desaquecimento: 1,5 km leve"
        ),
    )

    return [longao, tiros]


def main(profile: str, start: date) -> None:

    for i, session in enumerate(_samples()):

        on_date = start + timedelta(days=i)

        print(f"Empurrando '{session.workout_type}' para {on_date}...")

        result = push_session(profile, session, on_date)

        if result.get("ok"):

            print(f"  ✅ agendado (workout {result['workout_id']})")

        else:

            print(f"  ❌ falhou: {result.get('error')}")


if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Uso: python garmin_push_test.py <profile> [YYYY-MM-DD]")

        sys.exit(1)

    profile = sys.argv[1]

    start = (
        date.fromisoformat(sys.argv[2])
        if len(sys.argv) > 2
        else date.today() + timedelta(days=1)
    )

    main(profile, start)
