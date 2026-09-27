import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.planning.missed_workout_judge import MissedJudgment
from app.application.planner.missed_workout_flow import MissedWorkoutFlow
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.planner.missed_workout_flow"

WEEK = date(2026, 7, 6)
WEDNESDAY = date(2026, 7, 8)


def _session(day) -> PlannedSession:

    return PlannedSession(
        day=day, workout_type="Velocidade", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="4:45", target_pace_max="4:50",
    )


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=9.0, running_days=["Tuesday"],
        week_start=WEEK, sessions=[_session("Tuesday")],
    )


def _run(judgment, missed=True, last_notified=None, runner=None, ill=None):

    runner = runner or make_runner()

    proposal_repo = MagicMock()
    marker = MagicMock()
    marker.last_notified.return_value = last_notified

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as load_hist,
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.MissedWorkoutDetector") as detector,
        patch(f"{MODULE}.MissedWorkoutJudge") as judge,
        patch(f"{MODULE}.PlanProposalRepository", return_value=proposal_repo),
        patch(f"{MODULE}.MissedNotificationRepository", return_value=marker),
        patch.object(MissedWorkoutFlow, "_portrait", return_value="retrato"),
        patch(f"{MODULE}.IllnessEpisode.open", return_value=ill),
    ):

        load_runner.execute.return_value = runner
        load_hist.execute = AsyncMock(return_value=TrainingHistory([]))
        provider.for_profile = AsyncMock(return_value=(runner, _plan()))
        detector.yesterday_missed.return_value = (
            _session("Tuesday") if missed else None
        )
        judge.judge = AsyncMock(return_value=judgment)

        result = asyncio.run(
            MissedWorkoutFlow.process("renato", reference_date=WEDNESDAY)
        )

        judged = judge.judge.await_count

    return result, proposal_repo, marker, judged


def test_no_miss_returns_none():

    result, proposal_repo, marker, _ = _run(judgment=None, missed=False)

    assert result is None
    marker.mark.assert_not_called()


def test_low_impact_sends_message_without_a_proposal():

    judgment = MissedJudgment(message="Segue igual. 💪", operations=[])

    result, proposal_repo, marker, _ = _run(judgment=judgment)

    runner, message = result
    assert "Segue igual" in message
    proposal_repo.save.assert_not_called()      # nada a propor
    marker.mark.assert_called_once()            # marca pra não repetir


def test_meaningful_stores_a_proposal():

    judgment = MissedJudgment(
        message="Reorganizo seus próximos dias? ",
        operations=[{"action": "drop", "day": "Thursday"}],
    )

    result, proposal_repo, marker, _ = _run(judgment=judgment)

    assert result is not None
    saved = proposal_repo.save.call_args.args[1]
    assert saved.kind == "missed"
    assert saved.operations
    marker.mark.assert_called_once()


def test_already_notified_is_not_repeated():

    judgment = MissedJudgment(message="x", operations=[])

    # já avisamos o furo de ontem (terça 07/07)
    result, proposal_repo, marker, _ = _run(
        judgment=judgment, last_notified="2026-07-07",
    )

    assert result is None
    marker.mark.assert_not_called()


def test_external_coach_is_skipped():

    result, proposal_repo, marker, _ = _run(
        judgment=None, runner=make_runner(external_coach=True),
    )

    assert result is None


def test_sick_athlete_is_not_charged_for_the_miss():
    """Hélio 27/09: relatou resfriado e não voltou a correr — o motivo do furo
    já é conhecido; nada de "o que tá pegando?"."""

    judgment = MissedJudgment(message="o que tá pegando?", operations=[])

    result, proposal_repo, marker, judged = _run(judgment=judgment, ill=object())

    assert result is None
    assert judged == 0
    marker.mark.assert_not_called()
