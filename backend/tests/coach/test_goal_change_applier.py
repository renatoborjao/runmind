import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.goal_change_applier import (
    GoalChangeApplier,
)
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.goal_change_applier"


def test_not_a_goal_change_returns_none_without_calling_ia():

    runner = make_runner()

    with patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser:

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "como foi meu treino de ontem?",
            )
        )

    assert reply is None
    mock_parser.parse.assert_not_called()


def test_gate_passes_but_ia_finds_no_goal_falls_through():
    """Portão barato deu falso positivo ('prova' + 'agora'), mas a IA não
    achou uma declaração de objetivo de verdade -> segue o fluxo normal."""

    runner = make_runner()

    with (
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
    ):

        mock_parser.parse = AsyncMock(return_value={})

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "a prova que fiz agora foi ótima",
            )
        )

    assert reply is None
    mock_repo_cls.return_value.update_fields.assert_not_called()


def test_new_goal_updates_profile_regenerates_and_confirms():

    runner = make_runner(external_coach=False)

    with (
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "meia maratona sub-2h",
                "target_race": "21 km",
                "target_time": "02:00:00",
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        plan = MagicMock()

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, plan),
        )

        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero mudar minha meta pra meia sub-2h",
            )
        )

    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {
            "goal": "meia maratona sub-2h",
            "target_race": "21 km",
            "target_time": "02:00:00",
        },
    )

    mock_provider.for_profile.assert_awaited_once_with("renato", force=True)

    assert "meia maratona sub-2h" in reply
    assert "[PLANO]" in reply


def test_new_goal_without_race_details_does_not_wipe_existing_race():
    """'meu objetivo agora é só saúde' não deve apagar a prova já
    registrada (só quando o atleta disser explicitamente que mudou)."""

    runner = make_runner(
        target_race="10 km", target_time="00:50:00", race_date="2026-09-01",
    )

    with (
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "só saúde e constância",
                "target_race": None,
                "target_time": None,
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, MagicMock()),
        )

        mock_formatter.week_plan_message.return_value = "[PLANO]"

        asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "meu objetivo agora é só saúde",
            )
        )

    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"goal": "só saúde e constância"},
    )


def test_external_coach_only_records_without_regenerating():

    runner = make_runner(external_coach=True)

    with (
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={"goal": "correr mais leve"}
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero mudar meu objetivo pra correr mais leve",
            )
        )

    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"goal": "correr mais leve"},
    )

    mock_provider.for_profile.assert_not_awaited()

    assert "correr mais leve" in reply
