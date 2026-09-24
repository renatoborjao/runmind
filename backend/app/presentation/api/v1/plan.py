from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.presentation.api.deps import current_profile

router = APIRouter(
    prefix="/plan",
    tags=["Plan"],
)


@router.get("")
async def get_plan(profile: str = Depends(current_profile)):

    try:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            history=history,
        )

        return {
            "runner": asdict(runner),
            "assessment": asdict(assessment),
            "plan": asdict(plan),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.post("/push-watch")
async def push_watch(profile: str = Depends(current_profile)):
    """Empurra a semana atual do plano pro Garmin do atleta logado (o mesmo
    fluxo do 'quer no relógio? SIM'). Idempotente (reconcilia). Se o Garmin não
    estiver conectado, devolve um aviso amigável em vez de erro cru."""

    from app.application.garmin.push_current_plan import push_current_plan

    try:

        _, _, results = await push_current_plan(profile)

    except Exception as e:

        # relógio não conectado / falha de login etc. — não quebra a tela
        return {
            "ok": False,
            "message": "Não consegui falar com teu Garmin. Confere se o relógio está conectado.",
            "detail": str(e),
        }

    pushed = [r for r in results if r.get("ok")]

    return {
        "ok": True,
        "pushed": len(pushed),
        "message": (
            f"Mandei {len(pushed)} treino(s) pro teu Garmin. Sincroniza o relógio "
            "com o app que eles aparecem em Treino → Programados. 🏃"
            if pushed
            else "Teu relógio já está com os treinos da semana. 👍"
        ),
    }


_DAY_PT = {
    "Monday": "segunda", "Tuesday": "terça", "Wednesday": "quarta",
    "Thursday": "quinta", "Friday": "sexta", "Saturday": "sábado",
    "Sunday": "domingo",
}


class MoveIn(BaseModel):

    from_day: str
    to_day: str


@router.post("/move")
async def move_workout(body: MoveIn, profile: str = Depends(current_profile)):
    """Move um treino de dia PELO CALENDÁRIO — mesmo aplicador da troca no chat:
    efetiva no plano vivo (persiste) E registra na conversa pra o coach ficar a
    par (nada se perde). Só move pra dia LIVRE da semana do plano."""

    from datetime import datetime, timedelta

    from app.core.clock import now_local
    from app.application.coach.conversation.plan_change_applier import (
        PlanChangeApplier,
    )
    from app.domain.entities.plan_proposal import PlanProposal
    from app.infrastructure.persistence.conversation_repository import (
        ConversationRepository,
    )
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    from_day, to_day = body.from_day, body.to_day

    if from_day not in _DAY_PT or to_day not in _DAY_PT or from_day == to_day:

        raise HTTPException(status_code=400, detail="dias inválidos")

    plan = WeeklyPlanRepository().load(profile)

    if plan is None or not plan.sessions:

        raise HTTPException(status_code=400, detail="sem plano da semana")

    if plan.source == "externo":

        raise HTTPException(status_code=400, detail="plano externo não é remanejável aqui")

    source = plan.find_session_by_day(from_day)

    if source is None:

        raise HTTPException(status_code=400, detail="não há treino nesse dia")

    if plan.find_session_by_day(to_day) is not None:

        raise HTTPException(status_code=409, detail="o dia de destino já tem treino")

    # não dá pra mover um treino pra um dia que JÁ PASSOU (data BRT via clock,
    # nunca o relógio do cliente). week_start é a segunda do plano; o offset do
    # dia na semana dá a data do destino.
    to_date = plan.week_start + timedelta(days=list(_DAY_PT).index(to_day))

    if to_date < now_local().date():

        raise HTTPException(status_code=400, detail="esse dia já passou — escolhe um dia que ainda vem")

    session = asdict(source)
    session["day"] = to_day
    session.pop("garmin", None)
    session["structure"] = "\n".join(
        ln for ln in (session.get("structure") or "").split("\n")
        if not ln.strip().startswith("Dica:")
    )

    proposal = PlanProposal(
        kind="move",
        week_start=plan.week_start.isoformat(),
        preview=f"Mover {source.workout_type} de {from_day} para {to_day}",
        created_at=datetime.now().isoformat(),
        operations=[
            {"action": "drop", "day": from_day},
            {"action": "replace", "day": to_day, "session": session},
        ],
    )

    updated = PlanChangeApplier.apply(profile, proposal)

    if updated is None:

        raise HTTPException(status_code=409, detail="a semana virou — recarrega o plano")

    pt_from, pt_to = _DAY_PT[from_day], _DAY_PT[to_day]

    # o atleta JÁ confirmou no app ("tem certeza?" → sim) e a tela avisa que o
    # relógio vai junto — então quem tem Garmin recebe a semana atualizada na
    # hora. Se o Garmin falhar, o treino continua movido e a rede de segurança
    # do relógio (oferta no chat) cobre — nunca vira limbo. Ver [[project_rede_relogio]].
    watch = await _push_watch_after_move(profile)

    if watch == "sent":

        coach_tail = " Já atualizei teu relógio — sincroniza o Garmin que aparece em Treino → Programados. ⌚"

    elif watch == "failed":

        from app.application.garmin.watch_offer import watch_update_offer

        coach_tail = (
            " Não consegui falar com teu Garmin agora."
            + (watch_update_offer(profile) or " Toca em 'Enviar pro relógio' no app pra tentar de novo.")
        )

    else:

        coach_tail = " 👊"

    # coach a par: registra a troca na MESMA conversa (nada se perde)
    try:

        repo = ConversationRepository()
        repo.append_turn(profile, "user", f"(pelo app) movi meu treino de {pt_from} para {pt_to}")
        repo.append_turn(
            profile,
            "assistant",
            f"Feito! Movi teu {source.workout_type} de {pt_from} pra {pt_to}.{coach_tail}",
        )

    except Exception as e:

        print(f"Falha ao registrar move na conversa de '{profile}': {e}")

    message = f"Treino movido de {pt_from} para {pt_to}."

    if watch == "sent":

        message += " Relógio atualizado — sincroniza o Garmin. ⌚"

    elif watch == "failed":

        message += " Não consegui falar com teu Garmin agora; toca em 'Enviar pro relógio' pra tentar de novo."

    return {"ok": True, "message": message, "watch": watch}


async def _push_watch_after_move(profile: str) -> str:
    """Empurra a semana (já com o treino no dia novo) pro Garmin.
    'sent' | 'failed' | 'none' (sem Garmin conectado → nada a fazer)."""

    from app.application.garmin.push_current_plan import push_current_plan
    from app.infrastructure.integrations.garmin.garmin_client import GarminClient

    try:

        if not GarminClient.is_connected(profile):

            return "none"

        _, _, results = await push_current_plan(profile)

        # tinha o que mandar e NADA subiu = falhou (não finge sucesso)
        if results and not any(r.get("ok") for r in results):

            return "failed"

        return "sent"

    except Exception as e:

        print(f"Falha ao empurrar relógio após move de '{profile}': {e}")

        return "failed"