from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal
from tests.coach.factories import make_runner


def _ctx(learnings="", body_directive=""):

    runner = make_runner(preferred_running_days=["Tuesday", "Thursday"])

    goal = TrainingGoal(
        name="10k", distance_km=10.0, target_time=None, race_date=None,
    )

    metrics = RunnerMetrics(
        easy_pace_min=6.0,
        easy_pace_max=6.5,
        threshold_pace=5.0,
        vo2_pace=4.5,
        average_hr=150,
        max_long_run=12.0,
        weekly_volume=28.0,
    )

    baseline = RunnerBaseline(
        has_history=True,
        weekly_km=28.0,
        last_week_km=30.0,
        max_week_km=35.0,
        runs_per_week=3.0,
        typical_run_km=8.0,
        longest_km=12.0,
        trend="estável",
    )

    return PlanContextBuilder.build(
        runner=runner,
        goal=goal,
        metrics=metrics,
        baseline=baseline,
        recent_adherence=[],
        last_plan=None,
        memory="",
        weeks_to_race=None,
        learnings=learnings,
        body_directive=body_directive,
    )


def test_no_learnings_keeps_context_unchanged():
    """Flag off (default) => learnings="" => contexto idêntico ao de hoje."""

    assert _ctx(learnings="") == _ctx()
    assert "observando" not in _ctx()


def test_learnings_section_is_injected_when_present():

    section = (
        "O que o coach aprendeu observando ELE (comportamento e resultado, "
        "não o que ele fala):\n- [aderencia] Fura o longão de domingo (12/07)"
    )

    ctx = _ctx(learnings=section)

    assert "Fura o longão de domingo" in ctx
    assert "observando ELE" in ctx


def test_body_directive_is_injected_when_present():

    directive = (
        "STATUS DO CORPO (você é o COACH): o corpo dele está pedindo "
        "RECUPERAÇÃO."
    )

    ctx = _ctx(body_directive=directive)

    assert "pedindo RECUPERAÇÃO" in ctx


def test_no_body_directive_keeps_context_unchanged():

    assert _ctx(body_directive="") == _ctx()
    assert "STATUS DO CORPO" not in _ctx()
