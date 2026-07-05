from app.application.external_plan.external_plan_service import (
    ExternalPlanService,
)
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)
from tests.coach.factories import make_runner

SESSIONS = [
    {
        "day": "Tuesday",
        "workout_type": "Intervalado",
        "objective": "6x800m",
        "distance_km": 8.0,
        "duration_minutes": None,
        "pace_min": "5:30",
        "pace_max": "6:00",
        "notes": "descanso 2min",
    },
    {
        "day": "Saturday",
        "workout_type": "Longão",
        "objective": "Base",
        "distance_km": 14.0,
        "duration_minutes": None,
        "pace_min": None,
        "pace_max": None,
        "notes": "",
    },
]


def _isolated_repo(tmp_path, monkeypatch):

    repo = WeeklyPlanRepository()

    repo.storage = tmp_path

    monkeypatch.setattr(
        "app.application.external_plan.external_plan_service."
        "WeeklyPlanRepository",
        lambda: repo,
    )

    return repo


def test_apply_builds_and_saves_external_plan(tmp_path, monkeypatch):

    repo = _isolated_repo(tmp_path, monkeypatch)

    plan = ExternalPlanService.apply(
        "fulano",
        make_runner(name="Fulano"),
        SESSIONS,
    )

    assert plan.source == "externo"
    assert plan.phase == "EXTERNO"
    assert plan.weekly_volume == 22.0
    assert plan.running_days == ["Tuesday", "Saturday"]

    # week_start segue a régua do serviço (segunda da semana planejada;
    # no domingo já aponta pra próxima) — sem depender do dia real de hoje
    assert plan.week_start.weekday() == 0
    assert plan.week_start == WeeklyPlanService._week_start(today_local())

    # persistido e recarregável com source
    loaded = repo.load("fulano")
    assert loaded.source == "externo"
    assert len(loaded.sessions) == 2
    assert loaded.sessions[0].target_pace_min == "5:30"


def test_apply_filters_invalid_days_and_empty_sessions(
    tmp_path, monkeypatch,
):

    _isolated_repo(tmp_path, monkeypatch)

    sessions = [
        {"day": "Segunda", "workout_type": "Rodagem",
         "distance_km": 5.0},  # dia não normalizado -> filtrado
        {"day": "Monday", "workout_type": "Rodagem",
         "distance_km": None, "duration_minutes": None},  # sem medida
        {"day": "Friday", "workout_type": "Rodagem",
         "distance_km": 5.0},
    ]

    plan = ExternalPlanService.apply(
        "fulano",
        make_runner(),
        sessions,
    )

    assert [s.day for s in plan.sessions] == ["Friday"]


def test_apply_returns_none_when_nothing_usable(tmp_path, monkeypatch):

    repo = _isolated_repo(tmp_path, monkeypatch)

    plan = ExternalPlanService.apply(
        "fulano",
        make_runner(),
        [{"day": "???", "workout_type": "x"}],
    )

    assert plan is None
    assert repo.load("fulano") is None


def test_duration_only_session_is_kept(tmp_path, monkeypatch):

    _isolated_repo(tmp_path, monkeypatch)

    plan = ExternalPlanService.apply(
        "fulano",
        make_runner(),
        [{"day": "Wednesday", "workout_type": "Rodagem",
          "distance_km": None, "duration_minutes": 40}],
    )

    session = plan.sessions[0]
    assert session.planned_distance_km is None
    assert session.planned_duration_minutes == 40
