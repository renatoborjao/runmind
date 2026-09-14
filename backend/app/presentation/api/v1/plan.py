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

    from datetime import datetime

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

    # coach a par: registra a troca na MESMA conversa (nada se perde)
    try:

        repo = ConversationRepository()
        repo.append_turn(profile, "user", f"(pelo app) movi meu treino de {pt_from} para {pt_to}")
        repo.append_turn(
            profile,
            "assistant",
            f"Feito! Movi teu {source.workout_type} de {pt_from} pra {pt_to}. "
            "Toca em 'Enviar pro relógio' pra atualizar o Garmin. 👊",
        )

    except Exception as e:

        print(f"Falha ao registrar move na conversa de '{profile}': {e}")

    return {"ok": True, "message": f"Treino movido de {pt_from} para {pt_to}."}