from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal
from tests.coach.factories import make_runner


def _context(runner) -> str:

    return PlanContextBuilder.build(
        runner=runner,
        goal=TrainingGoal(
            name="10k", distance_km=10.0, target_time=None,
            race_date=None, priority="A",
        ),
        metrics=RunnerMetrics(
            easy_pace_min=6.0, easy_pace_max=6.5, threshold_pace=5.0,
            vo2_pace=4.5, average_hr=150, max_long_run=12.0,
            weekly_volume=28.0,
        ),
        baseline=RunnerBaseline(
            has_history=True, weekly_km=28.0, last_week_km=26.0,
            max_week_km=32.0, runs_per_week=3, typical_run_km=8.0,
            longest_km=12.0, trend="estável",
        ),
        recent_adherence=[],
        last_plan=None,
        memory="",
        weeks_to_race=None,
    )


def test_preferred_long_run_day_reaches_the_ai_as_a_soft_default():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
        preferred_long_run_day="Sunday",
    )

    context = _context(runner).lower()

    assert "longao" in context or "longão" in context
    assert "domingo" in context
    # é padrão, não regra fixa (o dinâmico pode sobrepor)
    assert "pode mudar" in context


def test_no_preferred_day_adds_no_long_run_line():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    context = _context(runner).lower()

    assert "por padrao ele faz o longao" not in context
    assert "por padrão ele faz o longão" not in context


def _context_with_report(report) -> str:

    return PlanContextBuilder.build(
        runner=make_runner(
            preferred_running_days=["Tuesday", "Thursday", "Saturday"],
        ),
        goal=TrainingGoal(
            name="10k", distance_km=10.0, target_time=None,
            race_date=None, priority="A",
        ),
        metrics=RunnerMetrics(
            easy_pace_min=6.0, easy_pace_max=6.5, threshold_pace=5.0,
            vo2_pace=4.5, average_hr=150, max_long_run=12.0,
            weekly_volume=28.0,
        ),
        baseline=RunnerBaseline(
            has_history=True, weekly_km=28.0, last_week_km=26.0,
            max_week_km=32.0, runs_per_week=3, typical_run_km=8.0,
            longest_km=12.0, trend="estável",
        ),
        recent_adherence=[0.66, 0.33],
        last_plan=None,
        memory="",
        weeks_to_race=None,
        adherence_report=report,
    )


def test_missed_pattern_reaches_the_ai_with_a_nudge_to_reposition():
    """O que ele vive furando não é bronca — é insumo pra a IA MOVER o
    treino em vez de prescrever de novo igual."""

    from app.domain.entities.adherence_report import (
        AdherenceReport,
        MissedPattern,
    )

    context = _context_with_report(
        AdherenceReport(
            missed_day=MissedPattern("Thursday", 3, 4),
            missed_type=MissedPattern("Intervalado", 3, 4),
        )
    )

    assert "quinta-feira (3 de 4 vezes que foi prescrita)" in context
    assert "treino de Intervalado (3 de 4)" in context
    assert "Não é preguiça" in context


def test_no_pattern_adds_no_line():
    """Sem padrão (ou sem report), o prompt não ganha ruído."""

    from app.domain.entities.adherence_report import AdherenceReport

    assert "deixa pra trás" not in _context_with_report(AdherenceReport())

    assert "deixa pra trás" not in _context_with_report(None)
