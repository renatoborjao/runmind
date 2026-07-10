"""Empurra o SEU plano real da semana pro Garmin (cada treino na sua data).
Use no lugar do garmin_push_test.py pra mandar os treinos de verdade que o
coach montou, não exemplos.

Pré-requisito: login feito (python garmin_login.py <profile>).

Uso:  python garmin_push_plan.py <profile>
Ex.:  python garmin_push_plan.py renato2
"""

import asyncio
import sys

from app.application.garmin.push_current_plan import push_current_plan


async def main(profile: str) -> None:

    runner, plan, results = await push_current_plan(profile)

    print(f"Plano de {runner.name} — semana de {plan.week_start}")
    print("=" * 50)

    if not results:

        print("Nenhuma sessão futura pra enviar (semana já passou?).")

        return

    for r in results:

        if r.get("ok"):

            print(f"[OK] {r['day']} ({r['date']}) - {r['workout']} "
                  f"-> Garmin (workout {r['workout_id']})")

        else:

            print(f"[FALHOU] {r['day']} ({r['date']}) - {r['workout']}: "
                  f"{r.get('error')}")


if __name__ == "__main__":

    if len(sys.argv) != 2:

        print("Uso: python garmin_push_plan.py <profile>")

        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
