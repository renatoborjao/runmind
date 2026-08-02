import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.plan_preference_applier import (
    PlanPreferenceApplier,
)
from app.application.coach.conversation.plan_preference_detector import (
    PlanPreference,
)
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.plan_preference_applier"


def _long_run_plan():

    long_session = MagicMock()
    long_session.workout_type = "LONG_RUN"
    plan = MagicMock()
    plan.sessions = [long_session]

    return plan


def test_valid_day_records_memory_regenerates_and_confirms():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(f"{MODULE}.watch_update_offer", return_value=""),
    ):

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, _long_run_plan()),
        )
        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato", runner, PlanPreference(long_run_day="Sunday"),
            )
        )

    # a preferência vira MEMÓRIA (dinâmica), não campo rígido
    ops = mock_memory.process.call_args.args[1]
    assert ops["add"][0]["category"] == "preferencia"
    assert "longão" in ops["add"][0]["content"]
    assert "Sunday" in ops["add"][0]["content"]

    mock_provider.for_profile.assert_awaited_once_with("renato", force=True)
    assert "Ajustei seu plano" in reply
    assert "domingo" in reply
    assert "[PLANO]" in reply
    assert "relógio" not in reply


def test_regenerated_plan_offers_watch_update():
    """Mudança de DIA do longão pra quem usa relógio: NÃO empurra sozinho —
    informa e OFERECE atualizar o relógio (⌚), pro 'sim' seguinte."""

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerMemoryService"),
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(
            f"{MODULE}.watch_update_offer",
            return_value="\n\n⌚ Quer no relógio? Responde sim.",
        ) as mock_offer,
    ):

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, _long_run_plan())
        )
        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato", runner, PlanPreference(long_run_day="Sunday"),
            )
        )

    mock_offer.assert_called_once_with("renato")
    assert "relógio" in reply


def test_beginner_without_long_run_records_preference_without_forcing():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.watch_update_offer", return_value=""),
    ):

        easy = MagicMock()
        easy.workout_type = "EASY"
        plan = MagicMock()
        plan.sessions = [easy]

        mock_provider.for_profile = AsyncMock(return_value=(runner, plan))

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato", runner, PlanPreference(long_run_day="Sunday"),
            )
        )

    # preferência registrada na memória pra quando o longão entrar
    mock_memory.process.assert_called_once()

    assert "Ajustei seu plano" not in reply
    assert "construir base" in reply
    assert "domingo" in reply


def test_day_outside_training_days_is_not_applied():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Saturday"],
    )

    with (
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato", runner, PlanPreference(long_run_day="Sunday"),
            )
        )

    # não grava nem regera quando o dia não é de treino
    mock_memory.process.assert_not_called()
    mock_provider.for_profile.assert_not_awaited()

    assert "não está nos seus dias" in reply
    assert "domingo" in reply


def test_external_coach_only_records_preference():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Sunday"],
        external_coach=True,
    )

    with (
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato", runner, PlanPreference(long_run_day="Sunday"),
            )
        )

    mock_memory.process.assert_called_once()
    mock_provider.for_profile.assert_not_awaited()

    assert "longão" in reply.lower()
