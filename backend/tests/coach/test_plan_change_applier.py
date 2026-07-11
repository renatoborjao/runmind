from dataclasses import asdict
from datetime import date
from unittest.mock import patch

from app.application.coach.conversation.plan_change_applier import (
    PlanChangeApplier,
)
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

MODULE = "app.application.coach.conversation.plan_change_applier"

WEEK = date(2026, 7, 6)


def _session(day, wt="Rodagem", dist=8.0, kind="run") -> PlannedSession:

    return PlannedSession(
        day=day,
        workout_type=wt,
        objective="",
        planned_distance_km=dist,
        planned_duration_minutes=None,
        target_pace_min="5:40",
        target_pace_max="5:55",
        kind=kind,
    )


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="IA",
        weekly_volume=0.0,
        running_days=[s.day for s in sessions],
        week_start=WEEK,
        sessions=list(sessions),
    )


def _repo(tmp_path) -> WeeklyPlanRepository:

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path / "plans"
    repo.storage.mkdir()

    return repo


def _proposal(operations, week_start=WEEK) -> PlanProposal:

    return PlanProposal(
        kind="aversion",
        week_start=week_start.isoformat(),
        preview="...",
        created_at="2026-07-07T09:00:00",
        operations=operations,
    )


def _apply(tmp_path, live, proposal, connected):

    repo = _repo(tmp_path)
    repo.save("renato", live)

    with (
        patch(f"{MODULE}.WeeklyPlanRepository", return_value=repo),
        patch(f"{MODULE}.GarminClient") as gc,
        patch(f"{MODULE}.GarminReconciler") as recon,
    ):

        gc.is_connected.return_value = connected

        updated = PlanChangeApplier.apply("renato", proposal)

    return updated, repo, recon


def test_replace_swaps_the_session_and_persists(tmp_path):

    live = _plan(
        _session("Tuesday"),
        _session("Thursday", wt="Velocidade", dist=9.0),
    )

    fartlek = _session("Thursday", wt="Fartlek", dist=9.0)

    proposal = _proposal(
        [{"action": "replace", "day": "Thursday",
          "session": asdict(fartlek)}]
    )

    updated, repo, recon = _apply(tmp_path, live, proposal, connected=False)

    assert updated.find_session_by_day("Thursday").workout_type == "Fartlek"
    recon.reconcile.assert_not_called()          # relógio desconectado

    # persistiu de verdade
    assert repo.load("renato").find_session_by_day(
        "Thursday"
    ).workout_type == "Fartlek"


def test_reconciles_the_watch_when_connected(tmp_path):

    live = _plan(
        _session("Tuesday"),
        _session("Thursday", wt="Velocidade", dist=9.0),
    )

    fartlek = _session("Thursday", wt="Fartlek", dist=9.0)

    proposal = _proposal(
        [{"action": "replace", "day": "Thursday",
          "session": asdict(fartlek)}]
    )

    updated, repo, recon = _apply(tmp_path, live, proposal, connected=True)

    recon.reconcile.assert_called_once()

    kwargs = recon.reconcile.call_args.kwargs

    # reconcilia o ANTES (Velocidade) contra o DEPOIS (Fartlek)
    assert kwargs["previous_plan"].find_session_by_day(
        "Thursday"
    ).workout_type == "Velocidade"
    assert kwargs["current_plan"].find_session_by_day(
        "Thursday"
    ).workout_type == "Fartlek"


def test_drop_removes_the_session(tmp_path):

    live = _plan(_session("Tuesday"), _session("Thursday"))

    proposal = _proposal([{"action": "drop", "day": "Thursday"}])

    updated, repo, recon = _apply(tmp_path, live, proposal, connected=False)

    assert updated.find_session_by_day("Thursday") is None
    assert "Thursday" not in updated.running_days


def test_stale_week_is_not_applied(tmp_path):

    live = _plan(_session("Tuesday"))

    # proposta de outra semana (o atleta demorou a responder): obsoleta
    proposal = _proposal(
        [{"action": "drop", "day": "Tuesday"}],
        week_start=date(2026, 7, 13),
    )

    updated, repo, recon = _apply(tmp_path, live, proposal, connected=False)

    assert updated is None
    # plano vivo intacto
    assert repo.load("renato").find_session_by_day("Tuesday") is not None
