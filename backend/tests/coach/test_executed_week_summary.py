from datetime import date, datetime

from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

WEEK = date(2026, 7, 6)   # segunda


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=28.0,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=WEEK,
        sessions=[
            PlannedSession("Tuesday", "Velocidade", "", 9.0,
                           None, None, None),
            PlannedSession("Thursday", "Rodagem", "", 8.0,
                           None, None, None),
            PlannedSession("Saturday", "Longão", "", 11.0,
                           None, None, None),
        ],
    )


def test_summarizes_executed_with_pace_and_matches_plan():

    acts = [
        make_activity(id=1, start_date=datetime(2026, 7, 7, 7, 0),
                      distance=8500.0, average_speed=3.0),   # terça
        make_activity(id=2, start_date=datetime(2026, 7, 11, 7, 0),
                      distance=11000.0, average_speed=3.3),  # sábado
    ]

    summary = ExecutedWeekSummary.build(_plan(), acts)

    assert "terça-feira: 8.5 km a 5:33/km (planejado: Velocidade)" in summary
    assert "sábado: 11.0 km" in summary
    # a quinta não foi feita
    assert "quinta-feira (Rodagem): não realizado" in summary


def test_extra_run_is_marked():

    # correu numa segunda (fora do plano) -> treino extra
    acts = [
        make_activity(id=9, start_date=datetime(2026, 7, 6, 7, 0),
                      distance=5000.0, average_speed=3.0),
    ]

    summary = ExecutedWeekSummary.build(_plan(), acts)

    assert "treino extra" in summary


def test_no_plan_returns_empty():

    assert ExecutedWeekSummary.build(None, []) == ""
