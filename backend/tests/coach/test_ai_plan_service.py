import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.planning.ai_plan_service import AIPlanService
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.planning.ai_plan_service"

WEEK = date(2026, 7, 6)


def _assessment(run_walk=False) -> TrainingAssessment:

    return TrainingAssessment(
        level="Intermediate", current_weekly_volume=28.0,
        recommended_weekly_volume=28.0, consistency=80.0, longest_run=12.0,
        available_training_days=3, goal="10k sub-50", observations=[],
        run_walk=run_walk,
    )


def _plan(source="runmind", week=WEEK) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=28.0, running_days=["Tuesday"], week_start=week,
        sessions=[], source=source,
    )


def _run(
    runner=None, assessment=None, ai_result=None,
    ai_error=None, existing=None, force=False,
):

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as repo_cls,
        patch(f"{MODULE}.CoachPlanEngine") as coach,
        patch(f"{MODULE}.WeeklyPlanService") as wps,
        patch.object(AIPlanService, "_build_context", return_value="ctx"),
    ):

        repo = repo_cls.return_value
        repo.load.return_value = existing

        wps._week_start.return_value = WEEK
        wps.get_or_generate.return_value = _plan(source="deterministico")

        if ai_error is not None:

            coach.generate = AsyncMock(side_effect=ai_error)

        else:

            coach.generate = AsyncMock(
                return_value=ai_result or _plan(),
            )

        plan = asyncio.run(
            AIPlanService.ensure_plan(
                "renato", runner or make_runner(),
                assessment or _assessment(),
                MagicMock(), MagicMock(), TrainingHistory([]), WEEK,
                force=force,
            )
        )

        return plan, coach, repo, wps


def test_ai_generates_and_saves_the_plan():

    plan, coach, repo, wps = _run()

    coach.generate.assert_awaited_once()
    repo.save.assert_called_once()
    wps.get_or_generate.assert_not_called()
    assert plan.source == "runmind"


def test_falls_back_to_deterministic_on_ai_failure():

    plan, coach, repo, wps = _run(ai_error=RuntimeError("gemini caiu"))

    coach.generate.assert_awaited_once()
    wps.get_or_generate.assert_called_once()   # fallback
    assert plan.source == "deterministico"


def test_run_walk_also_goes_through_ai():

    # iniciante run/walk agora é gerado pela IA (com dados do onboarding)
    plan, coach, repo, wps = _run(assessment=_assessment(run_walk=True))

    coach.generate.assert_awaited_once()
    wps.get_or_generate.assert_not_called()
    assert plan.source == "runmind"


def test_external_coach_skips_ai_and_uses_deterministic():

    plan, coach, repo, wps = _run(
        runner=make_runner(external_coach=True),
    )

    coach.generate.assert_not_awaited()
    wps.get_or_generate.assert_called_once()
    assert plan.source == "deterministico"


def test_cached_week_plan_is_reused():

    plan, coach, repo, wps = _run(existing=_plan(week=WEEK))

    coach.generate.assert_not_awaited()
    wps.get_or_generate.assert_not_called()
    assert plan.week_start == WEEK


def test_force_regenerates_by_ai_even_with_cached_plan():

    # o atleta pediu mudança: força regenerar PELA IA (mantém o plano rico),
    # nunca reaproveita o cache nem cai no determinístico
    plan, coach, repo, wps = _run(existing=_plan(week=WEEK), force=True)

    coach.generate.assert_awaited_once()
    wps.get_or_generate.assert_not_called()
    assert plan.source == "runmind"
