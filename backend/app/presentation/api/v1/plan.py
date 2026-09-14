from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

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