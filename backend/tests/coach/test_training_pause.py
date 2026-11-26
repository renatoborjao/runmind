"""Pausa pedida pelo atleta: nenhum plano nasce até ele pedir pra voltar."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.coach.conversation.coach_brain import BrainAction, CoachBrain
from app.application.coach.conversation.coach_brain_executor import CoachBrainExecutor
from app.application.coach.conversation.plan_change_applier import (
    DROP_NOTE,
    PlanChangeApplier,
)
from app.application.coach.conversation.proposal_reply_detector import (
    ProposalReplyDetector,
)
from app.application.coach.intelligence.training_pause import (
    PAUSED_SOURCE,
    TrainingPause,
)
from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.planner.weekly_plan_notifier import WeeklyPlanNotifier
from app.domain.entities.memory_entry import MemoryEntry
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

PAUSE = "app.application.coach.intelligence.training_pause"
SERVICE = "app.application.coach.planning.ai_plan_service"
EXECUTOR = "app.application.coach.conversation.coach_brain_executor"
APPLIER = "app.application.coach.conversation.plan_change_applier"
NOTIFIER = "app.application.planner.weekly_plan_notifier"

WEEK = date(2026, 11, 30)


def _plan(week_start=WEEK, sessions=()):

    return TrainingPlan(
        athlete_name="Fulano", objective="21k", phase="Base", weekly_volume=10.0,
        running_days=["Tuesday"], week_start=week_start, sessions=list(sessions),
    )


def _ensure(existing, force):

    generate = AsyncMock()

    with (
        patch(f"{SERVICE}.WeeklyPlanRepository") as repo,
        patch.object(AIPlanService, "_generate_ai", new=generate),
    ):
        repo.return_value.load.return_value = existing

        plan = asyncio.run(AIPlanService.ensure_plan(
            profile="fulano",
            runner=make_runner(paused_since="2026-11-25"),
            assessment=MagicMock(), metrics=MagicMock(), goal=MagicMock(),
            history=MagicMock(), reference_date=WEEK, force=force,
        ))

    return plan, generate, repo.return_value


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("existing", [None, _plan(date(2026, 11, 16))])
def test_paused_athlete_gets_no_new_plan(existing, force):

    plan, generate, repo = _ensure(existing, force)

    assert plan.source == PAUSED_SOURCE
    assert plan.sessions == []
    assert plan.week_start == WEEK
    generate.assert_not_called()
    repo.save.assert_not_called()


def test_paused_athlete_keeps_the_stored_week():

    stored = _plan()

    plan, generate, repo = _ensure(stored, True)

    assert plan is stored
    generate.assert_not_called()
    repo.save.assert_not_called()


def test_sunday_delivery_skips_a_paused_athlete():

    with (
        patch(f"{NOTIFIER}.LoadRunnerProfile") as load,
        patch(f"{NOTIFIER}.use_athlete_timezone"),
        patch(f"{NOTIFIER}.now_in") as now,
        patch(f"{NOTIFIER}.DispatchGuard") as guard,
        patch(f"{NOTIFIER}.AIPlanService") as service,
        patch(f"{NOTIFIER}.CoachOutbox") as outbox,
    ):
        load.execute.return_value = make_runner(paused_since="2026-11-25")
        now.return_value.weekday.return_value = 6
        now.return_value.hour = 20

        asyncio.run(WeeklyPlanNotifier._notify_one("fulano"))

    guard.mark.assert_not_called()
    service.ensure_plan.assert_not_called()
    outbox.send.assert_not_called()


def test_start_keeps_the_first_date():

    runner = make_runner(paused_since="2026-11-25")

    with patch(f"{PAUSE}.RunnerProfileRepository") as repo:
        TrainingPause.start("fulano", runner, date(2026, 12, 10))

    repo.return_value.update_fields.assert_called_once_with(
        "fulano", {"paused_since": "2026-11-25"},
    )


def test_end_clears_the_state_and_archives_the_pause_note():

    runner = make_runner(paused_since="2026-11-25")

    def entry(key, content, created):
        return MemoryEntry(
            id=key, category="disponibilidade", content=content,
            source="conversation", created_at=created, status="active",
        )

    with (
        patch(f"{PAUSE}.RunnerProfileRepository") as repo,
        patch(f"{PAUSE}.RunnerMemoryRepository") as memory,
    ):
        memory.return_value.active.return_value = [
            entry("a", "Pausa nos treinos até 31/12", "2026-11-25T13:00:02"),
            entry("b", "Viagem em outubro", "2026-10-01T10:00:00"),
            entry("c", "Corre terça e quinta", "2026-11-26T10:00:00"),
        ]

        assert TrainingPause.end("fulano", runner) is True

    repo.return_value.update_fields.assert_called_once_with(
        "fulano", {"paused_since": None},
    )
    memory.return_value.archive.assert_called_once_with("fulano", ["a"])
    assert runner.paused_since is None


def test_end_without_pause_does_nothing():

    with patch(f"{PAUSE}.RunnerProfileRepository") as repo:
        assert TrainingPause.end("fulano", make_runner()) is False

    repo.assert_not_called()


@pytest.mark.parametrize("kind", ["pause", "resume"])
def test_brain_reads_pause_and_resume(kind):

    decision = CoachBrain._parse(
        '{"say": "ok", "actions": [{"type": "%s", "scope": "week"}]}' % kind
    )

    assert [a.type for a in decision.all_actions] == [kind]


def _action(kind):

    return BrainAction(type=kind, scope="week", target_day=None, instruction="")


def test_pause_wins_over_a_skip_or_replan_in_the_same_message():

    with (
        patch(f"{EXECUTOR}.TrainingPause.start") as start,
        patch(f"{EXECUTOR}.FrequencyOfferStore") as offer,
        patch(f"{EXECUTOR}.PlanProposalRepository") as proposals,
        patch(f"{EXECUTOR}.OneOffProposalStore") as one_off,
        patch.object(
            CoachBrainExecutor, "_skip",
            new=AsyncMock(return_value=("🗓️ Tirei os treinos.", True)),
        ) as skip,
        patch.object(CoachBrainExecutor, "_replan", new=AsyncMock()) as replan,
    ):
        reply = asyncio.run(CoachBrainExecutor._act_all(
            "fulano", make_runner(),
            [_action("skip"), _action("pause"), _action("replan")],
            MagicMock(), "pausa", say="Combinado.",
        ))

    start.assert_called_once()
    offer.clear.assert_called_once_with("fulano")
    proposals.return_value.clear.assert_called_once_with("fulano")
    one_off.clear.assert_called_once_with("fulano")
    skip.assert_awaited_once()
    replan.assert_not_awaited()
    assert reply.startswith("Combinado.")
    assert "até você pedir pra voltar" in reply
    assert "Tirei os treinos" in reply


def test_resume_with_replan_ends_the_pause_before_rebuilding():

    order = []

    def end(profile, who):
        order.append("resume")
        who.paused_since = None
        return True

    async def replan(*args, **kwargs):
        order.append("replan")
        return "plano"

    with (
        patch(f"{EXECUTOR}.TrainingPause.end", side_effect=end),
        patch.object(CoachBrainExecutor, "_replan", new=replan),
    ):
        reply = asyncio.run(CoachBrainExecutor._act_all(
            "fulano", make_runner(paused_since="2026-11-25"),
            [_action("replan"), _action("resume")], MagicMock(), "bora voltar",
        ))

    assert order == ["resume", "replan"]
    assert "Pausa encerrada" in reply
    assert "plano" in reply


def test_resume_alone_delivers_the_plan_in_the_same_reply():

    def end(profile, who):
        who.paused_since = None
        return True

    replan = AsyncMock(return_value="plano da semana")

    with (
        patch(f"{EXECUTOR}.TrainingPause.end", side_effect=end),
        patch.object(CoachBrainExecutor, "_replan", new=replan),
    ):
        reply = asyncio.run(CoachBrainExecutor._act_all(
            "fulano", make_runner(paused_since="2026-11-25"), [_action("resume")],
            MagicMock(), "bora voltar",
        ))

    replan.assert_awaited_once()
    assert replan.await_args.kwargs["resumed"] is True
    assert "Pausa encerrada" in reply
    assert "plano da semana" in reply


def test_a_lone_replan_does_not_end_the_pause():

    runner = make_runner(paused_since="2026-11-25")

    with (
        patch(f"{EXECUTOR}.TrainingPause.end") as end,
        patch(
            "app.application.planner.current_plan_provider.CurrentPlanProvider."
            "for_profile",
            new=AsyncMock(),
        ) as provider,
    ):
        reply = asyncio.run(CoachBrainExecutor._act_all(
            "fulano", runner, [_action("replan")], MagicMock(), "refaz",
            say="Refiz tua semana!",
        ))

    end.assert_not_called()
    provider.assert_not_awaited()
    assert runner.paused_since == "2026-11-25"
    assert "em pausa" in reply
    assert "Refiz" not in reply


def test_dropping_sessions_at_his_request_is_written_on_the_plan():

    session = PlannedSession(
        day="Saturday", workout_type="Longão", objective="base",
        planned_distance_km=10.0, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None,
    )

    with patch(f"{APPLIER}.WeeklyPlanRepository") as repo:
        repo.return_value.load.return_value = _plan(sessions=[session])

        updated = PlanChangeApplier.apply("fulano", PlanProposal(
            kind="skip", week_start=WEEK.isoformat(), preview="",
            created_at="2026-12-01T10:00:00",
            operations=[{"action": "drop", "day": "Saturday"}],
        ))

    assert updated.route_note == DROP_NOTE


@pytest.mark.parametrize("text", [
    "sim", "Sim, pode!", "pode colocar a segunda", "não, deixa assim", "bora",
    "isso, 5 dias",
])
def test_short_replies_are_recognised(text):

    assert ProposalReplyDetector.is_short_reply(text)


@pytest.mark.parametrize("text", [
    "Boa!! Vamos tirar esse mês de dezembro de recuperação",
    "vamos descansar",
    "não vou conseguir correr hoje",
    "",
])
def test_other_subjects_are_not_a_short_reply(text):

    assert not ProposalReplyDetector.is_short_reply(text)
