"""Treino de HOJE de um atleta, exatamente como o coach prescreveu (usa o
formatter oficial que vai pro atleta). Se hoje é descanso, diz isso e mostra
o treino anterior e o próximo da semana — pra não deixar dúvida.

Resolve o fuso do atleta primeiro (o "hoje" é no fuso DELE, não no do
servidor): um atleta em Lisboa pode já estar no dia seguinte.

Uso:
  python show_today.py <profile>
"""

import sys

from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import today_local, use_athlete_timezone
from app.core.weekdays import weekday_name
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


def show(profile: str) -> None:

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    today = today_local()

    plan = WeeklyPlanRepository().load(profile)

    print(f"Atleta: {runner.name or profile}  (fuso: {runner.timezone})")
    print(f"Hoje para ele: {today} ({weekday_name(today)})")

    if plan is None:

        print("Sem plano carregado.")

        return

    print(f"Semana do plano: {plan.week_start}  ·  {plan.weekly_objective}")
    print()

    message = WeeklyPlanMessageFormatter.today_session_message(
        runner.name or profile,
        plan,
        reference_date=today,
        profile=profile,
    )

    if message is not None:

        print("── TREINO DE HOJE (como o atleta recebe) ──")
        print(message)
        print()
        return

    # hoje é descanso: mostra a semana inteira, marcando ontem/hoje/próximo
    print("── HOJE É DIA DE DESCANSO (sem treino prescrito) ──")
    print()
    print("Semana completa:")

    for session in sorted(plan.sessions, key=plan.session_date):

        session_date = plan.session_date(session)

        when = (
            "◀ passou"
            if session_date < today
            else ("▶ HOJE" if session_date == today else "· a vir")
        )

        dist = (
            f"{session.planned_distance_km:.0f} km"
            if session.planned_distance_km
            else (
                f"{session.planned_duration_minutes} min"
                if session.planned_duration_minutes
                else "—"
            )
        )

        pace = (
            f"  {session.target_pace_min}–{session.target_pace_max}/km"
            if session.target_pace_min
            else ""
        )

        print(
            f"  {session_date} {weekday_name(session_date):<9} {when:<9} "
            f"{session.workout_type} · {dist}{pace}"
        )

    print()


if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("uso: python show_today.py <profile>")

        sys.exit(1)

    show(sys.argv[1])
