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
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
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

    # dias JÁ CUMPRIDOS: não re-empurra treino que o atleta já fez (não volta
    # como "Programado" um treino concluído). Best-effort — sem histórico, não
    # pula nada. Ver [[project_rede_relogio]].
    done_days = await _fulfilled_days(profile, plan)

    if full_refresh:

        # apaga os templates FUTUROS AINDA NÃO FEITOS que estão no relógio e zera
        # os registros -> o reconciliador re-empurra do zero (semana inteira
        # fresca), e o relógio repovoa "Programado" como faz no domingo. Os
        # cumpridos ficam intactos.
        _purge_future(plan, reference, garmin, done_days)

        previous = None  # nada "já no relógio" -> reconcilia tudo como novo

    results = GarminReconciler.reconcile(
        profile,
        previous_plan=previous or plan,
        current_plan=plan,
        reference_date=reference,
        garmin=garmin,
        done_days=done_days,
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


async def _fulfilled_days(profile: str, plan: TrainingPlan) -> set[str]:
    """Dias da semana já CUMPRIDOS (casados com treino real no histórico).
    Best-effort: qualquer falha volta vazio (não pula nada)."""

    try:

        history = await LoadTrainingHistory.execute(profile=profile)

        return WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

    except Exception as e:  # noqa: BLE001 — best-effort

        print(f"fulfilled_days falhou p/ '{profile}': {e}")

        return set()


def _purge_future(
    plan: TrainingPlan,
    reference: date,
    garmin,
    done_days: set[str] | None = None,
) -> None:
    """Apaga do Garmin os templates das sessões FUTURAS AINDA NÃO FEITAS que já
    estão no relógio e zera seus registros — pra o reconciliador re-empurrar a
    semana fresca (o passado E os treinos já cumpridos ficam intactos).
    delete_workout cascateia o desagendamento, então não sobra treino nem
    agendamento antigo. Best-effort: falha numa remoção não derruba o re-push."""

    done = {d.lower() for d in (done_days or set())}

    for session in plan.sessions:

        if plan.session_date(session) < reference:

            continue  # o que já passou fica como está

        if session.day.lower() in done:

            continue  # treino já cumprido: não mexe (não volta como programado)

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
