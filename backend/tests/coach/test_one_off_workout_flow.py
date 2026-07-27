import asyncio
from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.one_off_workout_flow import (
    OneOffWorkoutFlow,
)
from app.application.coach.planning.one_off_workout_engine import OneOffWorkout
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.one_off_workout_flow"

# 2026-07-27 é segunda; o domingo dessa semana é 02/08
MONDAY = date(2026, 7, 27)


def _plan(sessions, source="externo") -> TrainingPlan:
    return TrainingPlan(
        athlete_name="Mauricio",
        objective="21 km",
        phase="EXTERNO",
        weekly_volume=0,
        running_days=[s.day for s in sessions],
        week_start=MONDAY,
        sessions=sessions,
        source=source,
    )


def _session(day, wtype="Rodagem", dist=8.0) -> PlannedSession:
    return PlannedSession(
        day=day, workout_type=wtype, objective="",
        planned_distance_km=dist, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None, kind="run",
    )


def _oneoff_result():
    return OneOffWorkout(
        session={
            "day": "Sunday", "workout_type": "Longão leve",
            "objective": "base", "planned_distance_km": 12.0,
            "planned_duration_minutes": None, "target_pace_min": "6:00",
            "target_pace_max": "6:30", "kind": "run",
            "structure": "12 km leves", "purpose": "base", "steps": [],
            "origin": "oneoff",
        },
        message="Montei um longão leve pra domingo, complementando ter/qui 💪",
    )


def _run(coro):
    return asyncio.run(coro)


def _enter_common(stack, plan, engine_result=None, garmin_connected=True):
    """Entra os mocks do fluxo no ExitStack. Retorna o repo de plano mockado
    (pra assertar o save)."""

    plan_repo = MagicMock()

    stack.enter_context(patch(f"{MODULE}.today_local", return_value=MONDAY))
    stack.enter_context(patch(
        f"{MODULE}.CurrentPlanProvider.for_profile",
        new=AsyncMock(return_value=(None, plan)),
    ))
    stack.enter_context(patch(
        f"{MODULE}.LoadTrainingHistory.execute",
        new=AsyncMock(return_value=SimpleNamespace(activities=[])),
    ))
    stack.enter_context(
        patch(f"{MODULE}.build_portrait", return_value="retrato")
    )
    stack.enter_context(
        patch(f"{MODULE}.ExecutedWeekSummary.build", return_value="contexto")
    )
    stack.enter_context(patch(
        f"{MODULE}.OneOffWorkoutEngine.build",
        new=AsyncMock(return_value=engine_result),
    ))
    stack.enter_context(
        patch(f"{MODULE}.WeeklyPlanRepository", return_value=plan_repo)
    )
    stack.enter_context(patch(
        f"{MODULE}.GarminClient.is_connected", return_value=garmin_connected,
    ))
    stack.enter_context(patch(f"{MODULE}.OneOffOfferStore"))

    return plan_repo


def test_ignores_non_request():

    runner = make_runner(external_coach=True)

    reply = _run(
        OneOffWorkoutFlow.handle("mauricio", runner, "como foi meu treino?")
    )

    assert reply is None


def test_asks_for_day_when_no_date():

    runner = make_runner(external_coach=True)

    with patch(f"{MODULE}.today_local", return_value=MONDAY):

        reply = _run(
            OneOffWorkoutFlow.handle(
                "mauricio", runner, "monta um treino pra mim"
            )
        )

    assert reply is not None
    assert "qual dia" in reply.lower()


def test_external_coach_fills_empty_day_and_offers_watch():
    """Treinador externo (ter/qui do treinador), domingo vazio: monta o
    avulso, grava origin=oneoff e oferece o relógio."""

    runner = make_runner(external_coach=True)

    plan = _plan([_session("Tuesday"), _session("Thursday")])

    with ExitStack() as stack:

        plan_repo = _enter_common(
            stack, plan, engine_result=_oneoff_result()
        )

        reply = _run(
            OneOffWorkoutFlow.handle(
                "mauricio", runner, "monta um treino pra domingo"
            )
        )

    # respondeu com a mensagem do motor + o treino
    assert "Montei um longão leve" in reply
    assert "domingo" in reply.lower()
    # ofereceu o relógio
    assert "relógio" in reply.lower()

    # gravou a sessão avulsa no plano
    plan_repo.save.assert_called_once()
    saved_plan = plan_repo.save.call_args.args[1]
    sunday = saved_plan.find_session_by_day("Sunday")
    assert sunday is not None
    assert sunday.origin == "oneoff"
    # não apagou o que o treinador deixou
    assert saved_plan.find_session_by_day("Tuesday") is not None


def test_managed_athlete_with_session_that_day_points_to_it():
    """Atleta NOSSO que já tem treino no dia: aponta o existente, não monta
    outro (não duplica)."""

    runner = make_runner(external_coach=False)

    plan = _plan([_session("Sunday", wtype="Longão")], source="runmind")

    with ExitStack() as stack:

        plan_repo = _enter_common(
            stack, plan, engine_result=_oneoff_result()
        )

        reply = _run(
            OneOffWorkoutFlow.handle(
                "renato2", runner, "monta um treino pra domingo"
            )
        )

    assert "já tem" in reply.lower()
    plan_repo.save.assert_not_called()


def test_managed_athlete_extra_on_empty_day_builds():
    """Atleta nosso pedindo treino num dia de folga (sem sessão): monta o
    extra sem mexer no resto."""

    runner = make_runner(external_coach=False)

    plan = _plan([_session("Saturday", wtype="Longão")], source="runmind")

    with ExitStack() as stack:

        plan_repo = _enter_common(
            stack, plan, engine_result=_oneoff_result()
        )

        reply = _run(
            OneOffWorkoutFlow.handle(
                "renato2", runner, "monta um treino extra pra domingo"
            )
        )

    assert "Montei" in reply
    plan_repo.save.assert_called_once()


def test_watch_reply_yes_pushes():

    runner = make_runner(external_coach=True)

    with (
        patch(
            f"{MODULE}.OneOffOfferStore.pending_date",
            return_value=date(2026, 8, 2),
        ),
        patch(f"{MODULE}.OneOffOfferStore.clear") as mock_clear,
        patch(
            f"{MODULE}.push_one_off",
            new=AsyncMock(return_value={"ok": True, "date": "2026-08-02"}),
        ) as mock_push,
    ):

        reply = _run(
            OneOffWorkoutFlow.resolve_watch_reply("mauricio", runner, "sim")
        )

    mock_push.assert_awaited_once()
    mock_clear.assert_called_once_with("mauricio")
    assert "Garmin" in reply


def test_watch_reply_no_declines_without_push():

    runner = make_runner(external_coach=True)

    with (
        patch(
            f"{MODULE}.OneOffOfferStore.pending_date",
            return_value=date(2026, 8, 2),
        ),
        patch(f"{MODULE}.OneOffOfferStore.clear"),
        patch(f"{MODULE}.push_one_off", new=AsyncMock()) as mock_push,
    ):

        reply = _run(
            OneOffWorkoutFlow.resolve_watch_reply("mauricio", runner, "não")
        )

    mock_push.assert_not_awaited()
    assert reply is not None


def test_watch_reply_none_when_no_pending_offer():

    runner = make_runner(external_coach=True)

    with patch(
        f"{MODULE}.OneOffOfferStore.pending_date", return_value=None
    ):

        reply = _run(
            OneOffWorkoutFlow.resolve_watch_reply("mauricio", runner, "sim")
        )

    assert reply is None
