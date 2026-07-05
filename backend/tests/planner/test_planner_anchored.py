from datetime import date

from app.application.planner.planner import TrainingPlanner
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_assessment import TrainingAssessment
from tests.coach.factories import make_runner

WEEK_START = date(2026, 7, 6)

DAYS = ["Tuesday", "Thursday", "Saturday", "Sunday"]


def _assessment(longest=12.0) -> TrainingAssessment:

    return TrainingAssessment(
        level="Intermediate",
        current_weekly_volume=15.0,
        recommended_weekly_volume=16.2,
        consistency=80.0,
        longest_run=longest,
        available_training_days=4,
        goal="Saúde",
        observations=[],
        run_walk=False,
    )


def _metrics() -> RunnerMetrics:

    return RunnerMetrics(
        easy_pace_min=6.0, easy_pace_max=6.5, threshold_pace=5.5,
        vo2_pace=5.0, average_hr=0, max_long_run=12.0, weekly_volume=15.0,
    )


def _baseline(typical=7.0, longest=12.0) -> RunnerBaseline:

    return RunnerBaseline(
        has_history=True, weekly_km=15.0, last_week_km=15.0,
        max_week_km=18.0, runs_per_week=4.0,
        typical_run_km=typical, longest_km=longest, trend="estável",
    )


def _runner():

    return make_runner(
        preferred_running_days=DAYS, weekly_training_days=4,
    )


def test_anchored_plan_hits_target_and_keeps_a_real_long_run():

    goal = BuildTrainingGoal.execute(_runner())

    plan = TrainingPlanner.generate(
        _runner(), _assessment(), goal, _metrics(), WEEK_START,
        training_week=1, baseline=_baseline(), target_volume=16.2,
    )

    total = sum(s.planned_distance_km or 0 for s in plan.sessions)

    # o volume-alvo da progressão é respeitado
    assert plan.weekly_volume == 16.2
    assert abs(total - 16.2) < 0.6

    # longão pela capacidade (não encolhido pela escala das outras sessões)
    long = next(s for s in plan.sessions if s.workout_type == "LONG_RUN")
    assert long.planned_distance_km >= 8.0


def test_without_baseline_falls_back_to_recommended_volume():

    goal = BuildTrainingGoal.execute(_runner())

    plan = TrainingPlanner.generate(
        _runner(), _assessment(), goal, _metrics(), WEEK_START,
        training_week=1,
    )

    # caminho antigo: volume = recommended do assessment
    assert plan.weekly_volume == 16.2


def test_target_volume_drives_the_week_not_recommended():

    goal = BuildTrainingGoal.execute(_runner())

    # alvo da progressão menor que o recommended -> o alvo manda
    plan = TrainingPlanner.generate(
        _runner(), _assessment(), goal, _metrics(), WEEK_START,
        training_week=1, baseline=_baseline(), target_volume=12.0,
    )

    assert plan.weekly_volume == 12.0
