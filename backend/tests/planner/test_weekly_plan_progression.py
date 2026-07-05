from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity, make_runner

CURRENT_WEEK = date(2026, 7, 6)      # segunda
PREVIOUS_WEEK = date(2026, 6, 29)    # segunda anterior


def _assessment(consistency=80.0) -> TrainingAssessment:

    return TrainingAssessment(
        level="Intermediate", current_weekly_volume=15.0,
        recommended_weekly_volume=16.2, consistency=consistency,
        longest_run=12.0, available_training_days=4, goal="Saúde",
        observations=[], run_walk=False,
    )


def _recent_history() -> TrainingHistory:

    # duas corridas por semana nas últimas semanas
    acts = []
    aid = 1
    for week in range(4):
        base = PREVIOUS_WEEK - timedelta(weeks=week)
        for offset in (1, 5):
            when = datetime(base.year, base.month, base.day) + timedelta(
                days=offset, hours=7,
            )
            acts.append(make_activity(
                id=aid, start_date=when, distance=6000.0, average_speed=3.0,
            ))
            aid += 1
    return TrainingHistory(activities=acts)


def test_no_history_skips_progression():

    runner = make_runner()
    goal = BuildTrainingGoal.execute(runner)

    baseline, target = WeeklyPlanService._progression(
        "p", runner, _assessment(), goal, None, None, CURRENT_WEEK,
    )

    assert baseline is None
    assert target is None


def test_progression_returns_baseline_and_positive_target():

    runner = make_runner()
    goal = BuildTrainingGoal.execute(runner)      # Saúde, sem prova
    repo = SimpleNamespace(history=lambda profile: [])  # sem plano anterior

    baseline, target = WeeklyPlanService._progression(
        "p", runner, _assessment(consistency=100.0),
        goal, _recent_history(), repo, CURRENT_WEEK,
    )

    assert baseline is not None
    assert baseline.weekly_km > 0
    assert target > 0


def test_last_week_adherence_from_previous_plan():

    previous = TrainingPlan(
        athlete_name="Renato", objective="Saúde", phase="BUILD",
        weekly_volume=10.0, running_days=["Tuesday", "Thursday"],
        week_start=PREVIOUS_WEEK,
        sessions=[
            PlannedSession("Tuesday", "EASY", "", 5.0, None, None, None),
            PlannedSession("Thursday", "EASY", "", 5.0, None, None, None),
        ],
    )

    repo = SimpleNamespace(history=lambda profile: [previous])

    # treinou só na terça da semana anterior (30/06) -> 1 de 2 = 0.5
    ran_tuesday = make_activity(
        id=1, start_date=datetime(2026, 6, 30, 7, 0, 0), distance=5000.0,
    )

    adherence = WeeklyPlanService._last_week_adherence(
        "p", repo, TrainingHistory([ran_tuesday]), CURRENT_WEEK,
    )

    assert adherence == 0.5


def test_adherence_none_without_previous_plan():

    repo = SimpleNamespace(history=lambda profile: [])

    adherence = WeeklyPlanService._last_week_adherence(
        "p", repo, TrainingHistory([]), CURRENT_WEEK,
    )

    assert adherence is None
