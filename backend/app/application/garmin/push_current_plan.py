"""Empurra o plano REAL da semana do atleta pro Garmin — cada sessão de
corrida na sua data do calendário. É isto que o fluxo opt-in ('quer no
relógio? SIM') vai chamar: manda os treinos de verdade que o coach montou,
não exemplos.

Passa pela reconciliação: o plano guarda o que já pôs no relógio, então
chamar de novo NÃO duplica — só empurra o que falta ou mudou."""

from datetime import date

from app.application.garmin.garmin_push import sweep_orphan_workouts
from app.application.garmin.garmin_reconciler import GarminReconciler
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.pushed_plan_store import PushedPlanStore
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


async def push_current_plan(
    profile: str,
    only_future: bool = True,
    full_refresh: bool = True,
) -> tuple[RunnerProfile, TrainingPlan, list[dict]]:
    """Sobe as sessões de corrida da semana atual pro Garmin do atleta.
    only_future descarta os dias que já passaram (não reagenda o que ficou
    pra trás). Retorna (runner, plano, resultados por sessão).

    full_refresh (padrão): re-empurra a semana INTEIRA fresca (apaga os
    templates futuros e recria+reagenda tudo), replicando o disparo de DOMINGO.
    É o único jeito de o relógio repovoar a aba "Programado" — uma mudança
    incremental de 1 item NÃO repovoa (confirmado no FR165 do Renato): o item
    novo cai em "Meus treinos" e "Programado" fica vazio. Ver
    [[project_rede_relogio]]."""

    runner, plan = await CurrentPlanProvider.for_profile(profile)

    reference = today_local() if only_future else date.min

    # conecta UMA vez e reusa em todas as ops (antes: um login por sessão)
    garmin = GarminClient.connect(profile)

    # reconcilia o plano ATUAL contra o ÚLTIMO que foi empurrado (snapshot).
    # Assim, se o plano foi REGENERADO desde o último push (troca de dia,
    # ritmo, etc.), o reconciliador remove os NOSSOS treinos antigos e empurra
    # os novos — sem duplicar nem orfanar. Primeira vez (sem snapshot):
    # reconcilia contra si mesmo (empurra tudo, idempotente).
    previous = PushedPlanStore.load(profile)

    if full_refresh:

        # apaga os templates FUTUROS que já estão no relógio e zera os registros
        # -> o reconciliador re-empurra tudo do zero (semana inteira fresca),
        # e o relógio, ao sincronizar, repovoa "Programado" como faz no domingo.
        _purge_future(plan, reference, garmin)

        previous = None  # nada "já no relógio" -> reconcilia tudo como novo

    results = GarminReconciler.reconcile(
        profile,
        previous_plan=previous or plan,
        current_plan=plan,
        reference_date=reference,
        garmin=garmin,
    )

    # persiste os registros de push (workout_id/schedule_id) gravados nas
    # sessões, pra próxima mudança saber o que já está no relógio
    WeeklyPlanRepository().save(profile, plan)

    # snapshot do que ficou no relógio agora — base da próxima reconciliação
    PushedPlanStore.save(profile, plan)

    # VARREDURA: apaga treinos NOSSOS órfãos (semanas/rebrand passados) que a
    # reconciliação por snapshot não pegou — mantém só os do plano atual. Os
    # avulsos ficam (estão no plano). Best-effort, nunca derruba o push.
    keep_ids = {
        session.garmin["workout_id"]
        for session in plan.sessions
        if session.garmin and session.garmin.get("workout_id")
    }

    sweep_orphan_workouts(profile, keep_ids, garmin)

    return runner, plan, results


def _purge_future(plan: TrainingPlan, reference: date, garmin) -> None:
    """Apaga do Garmin os templates das sessões FUTURAS que já estão no relógio
    e zera seus registros — pra o reconciliador re-empurrar a semana inteira
    fresca (o passado fica intacto). delete_workout cascateia o desagendamento,
    então não sobra treino nem agendamento antigo. Best-effort: falha numa
    remoção não derruba o re-push."""

    for session in plan.sessions:

        if plan.session_date(session) < reference:

            continue  # o que já passou fica como está

        record = session.garmin or {}

        workout_id = record.get("workout_id")

        if workout_id:

            try:

                garmin.delete_workout(workout_id)

            except Exception as e:  # noqa: BLE001 — best-effort

                print(
                    f"Purge (full refresh): falha ao apagar "
                    f"{session.day} wid={workout_id}: {e}"
                )

        session.garmin = None
