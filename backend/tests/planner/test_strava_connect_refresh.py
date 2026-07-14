import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.planner.strava_connect_refresh import (
    StravaConnectRefresh,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.planner.strava_connect_refresh"


def _plan() -> TrainingPlan:

    days = ["Tuesday", "Thursday", "Saturday"]

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="BUILD",
        weekly_volume=20.0, running_days=days,
        week_start=date(2026, 7, 13),
        sessions=[
            PlannedSession(
                day=d, workout_type="EASY", objective="Base",
                planned_distance_km=8.0, planned_duration_minutes=None,
                target_pace_min="6:00", target_pace_max="6:30", kind="run",
            )
            for d in days
        ],
    )


def _run(runner, *, is_done=False, should_offer=False):

    plan = _plan()

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as history,
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.NotificationService") as notifier,
        patch(f"{MODULE}.GarminSync") as garmin_sync,
        patch(f"{MODULE}.GarminOfferStore") as offer_store,
        patch(f"{MODULE}.StravaRefreshStore") as refresh_store,
    ):

        load_runner.execute.return_value = runner
        history.execute = AsyncMock()
        provider.for_profile = AsyncMock(return_value=(runner, plan))
        notifier.send = AsyncMock()
        garmin_sync.should_offer.return_value = should_offer
        garmin_sync.offer_text.return_value = "\n\n⌚ OFERTA"
        refresh_store.is_done.return_value = is_done

        asyncio.run(StravaConnectRefresh.refresh("fulano"))

        return {
            "history": history,
            "provider": provider,
            "notifier": notifier,
            "offer_store": offer_store,
            "refresh_store": refresh_store,
        }


def test_regenerates_and_sends_for_runmind_athlete():
    """Atleta do RunMind (sem treinador externo), primeira conexão: regenera
    o plano da semana com force e manda a mensagem; marca como feito."""

    m = _run(make_runner(external_coach=False))

    m["provider"].for_profile.assert_awaited_once_with("fulano", force=True)

    m["notifier"].send.assert_awaited_once()
    message = m["notifier"].send.call_args[0][1]
    assert "refiz seu plano" in message.lower()

    m["refresh_store"].mark.assert_called_once_with("fulano")


def test_external_coach_only_archives_history():
    """Treinador externo: o plano é do treinador. Arquiva o histórico e sai —
    não regenera nem manda plano."""

    m = _run(make_runner(external_coach=True))

    m["history"].execute.assert_awaited_once_with(profile="fulano")
    m["provider"].for_profile.assert_not_awaited()
    m["notifier"].send.assert_not_awaited()
    m["refresh_store"].mark.assert_not_called()


def test_already_refreshed_does_not_resend():
    """Já regenerou antes (reconexão): não re-dispara plano/mensagem, mas
    mantém o histórico arquivado."""

    m = _run(make_runner(external_coach=False), is_done=True)

    m["history"].execute.assert_awaited_once_with(profile="fulano")
    m["provider"].for_profile.assert_not_awaited()
    m["notifier"].send.assert_not_awaited()
    m["refresh_store"].mark.assert_not_called()


def test_appends_garmin_offer_when_connected():
    """Garmin conectado: anexa a oferta de mandar pro relógio e marca a
    oferta como pendente (pra entender o 'SIM')."""

    m = _run(make_runner(external_coach=False), should_offer=True)

    message = m["notifier"].send.call_args[0][1]
    assert "OFERTA" in message

    m["offer_store"].set_pending.assert_called_once_with("fulano")
