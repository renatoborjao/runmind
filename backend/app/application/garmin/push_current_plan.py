"""Empurra o plano REAL da semana do atleta pro Garmin — cada sessão de
corrida na sua data do calendário. É isto que o fluxo opt-in ('quer no
relógio? SIM') vai chamar: manda os treinos de verdade que o coach montou,
não exemplos.

Passa pela reconciliação: o plano guarda o que já pôs no relógio, então
chamar de novo NÃO duplica — só empurra o que falta ou mudou."""

from datetime import date

from app.application.garmin.garmin_reconciler import GarminReconciler
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.core.clock import today_local
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


async def push_current_plan(
    profile: str,
    only_future: bool = True,
) -> tuple[RunnerProfile, TrainingPlan, list[dict]]:
    """Sobe as sessões de corrida da semana atual pro Garmin do atleta.
    only_future descarta os dias que já passaram (não reagenda o que ficou
    pra trás). Retorna (runner, plano, resultados por sessão)."""

    runner, plan = await CurrentPlanProvider.for_profile(profile)

    reference = today_local() if only_future else date.min

    # conecta UMA vez e reusa em todas as ops (antes: um login por sessão)
    garmin = GarminClient.connect(profile)

    # o plano é o anterior E o atual: reconciliar contra ele mesmo empurra o
    # que falta e ignora o que já está lá igual (idempotente)
    results = GarminReconciler.reconcile(
        profile,
        previous_plan=plan,
        current_plan=plan,
        reference_date=reference,
        garmin=garmin,
    )

    # persiste os registros de push (workout_id/schedule_id) gravados nas
    # sessões, pra próxima mudança saber o que já está no relógio
    WeeklyPlanRepository().save(profile, plan)

    return runner, plan, results
