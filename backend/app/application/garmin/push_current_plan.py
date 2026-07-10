"""Empurra o plano REAL da semana do atleta pro Garmin — cada sessão de
corrida na sua data do calendário. É isto que o fluxo opt-in ('quer no
relógio? SIM') vai chamar: manda os treinos de verdade que o coach montou,
não exemplos."""

from app.application.garmin.garmin_push import push_session
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan

_RUNNING_KINDS = {"run", "walk", "run_walk"}


async def push_current_plan(
    profile: str,
    only_future: bool = True,
) -> tuple[RunnerProfile, TrainingPlan, list[dict]]:
    """Sobe as sessões de corrida da semana atual pro Garmin do atleta.
    only_future descarta os dias que já passaram (não reagenda o que ficou
    pra trás). Retorna (runner, plano, resultados por sessão)."""

    runner, plan = await CurrentPlanProvider.for_profile(profile)

    today = today_local()

    results: list[dict] = []

    for session in plan.sessions:

        if session.kind not in _RUNNING_KINDS:

            continue

        on_date = plan.session_date(session)

        if only_future and on_date < today:

            continue

        try:

            outcome = push_session(profile, session, on_date)

        except Exception as e:

            outcome = {"ok": False, "error": str(e)}

            print(f"Falha ao empurrar {session.day} pro Garmin: {e}")

        results.append(
            {
                "day": session.day,
                "date": on_date.isoformat(),
                "workout": session.workout_type,
                **outcome,
            }
        )

    return runner, plan, results
