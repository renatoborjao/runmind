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


def test_valid_day_updates_profile_regenerates_and_confirms():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(
            f"{MODULE}.resync_watch_if_pushed",
            new=AsyncMock(return_value=False),
        ),
    ):

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        # plano regerado tem um longão (atleta intermediário+)
        long_session = MagicMock()
        long_session.workout_type = "LONG_RUN"
        plan = MagicMock()
        plan.sessions = [long_session]

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, plan),
        )

        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato",
                runner,
                PlanPreference(long_run_day="Sunday"),
            )
        )

    # gravou a preferência no perfil
    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"preferred_long_run_day": "Sunday"},
    )

    # regerou o plano da semana forçando (força=True)
    mock_provider.for_profile.assert_awaited_once_with("renato", force=True)

    assert "Ajustei seu plano" in reply
    assert "domingo" in reply
    assert "[PLANO]" in reply
    # não sincronizou (nunca empurrou): sem nota de relógio
    assert "relógio" not in reply


def test_regenerated_plan_synced_to_watch_adds_note():
    """Quem JÁ tinha os treinos no relógio: ao regerar por preferência, o
    Garmin é ressincronizado e a resposta avisa (⌚)."""

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
        patch(
            f"{MODULE}.resync_watch_if_pushed",
            new=AsyncMock(return_value=True),
        ) as mock_resync,
    ):

        mock_repo_cls.return_value = MagicMock()

        long_session = MagicMock()
        long_session.workout_type = "LONG_RUN"
        plan = MagicMock()
        plan.sessions = [long_session]

        mock_provider.for_profile = AsyncMock(return_value=(runner, plan))
        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato",
                runner,
                PlanPreference(long_run_day="Sunday"),
            )
        )

    # ressincronizou o plano REGERADO contra o snapshot do relógio
    mock_resync.assert_awaited_once_with("renato", plan)
    assert "relógio" in reply


def test_beginner_without_long_run_records_preference_without_forcing():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(
            f"{MODULE}.resync_watch_if_pushed",
            new=AsyncMock(return_value=False),
        ),
    ):

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        # plano de iniciante: só rodagens, sem longão
        easy = MagicMock()
        easy.workout_type = "EASY"
        plan = MagicMock()
        plan.sessions = [easy]

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, plan),
        )

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato",
                runner,
                PlanPreference(long_run_day="Sunday"),
            )
        )

    # preferência é registrada pra quando o longão entrar
    mock_repo.update_fields.assert_called_once()

    # mas não confirma um ajuste de longão que ainda não existe
    assert "Ajustei seu plano" not in reply
    assert "construir base" in reply
    assert "domingo" in reply


def test_day_outside_training_days_is_not_applied():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Saturday"],
    )

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato",
                runner,
                PlanPreference(long_run_day="Sunday"),
            )
        )

    # não força nada quando o dia não é de treino
    mock_repo.update_fields.assert_not_called()
    mock_provider.for_profile.assert_not_awaited()

    assert "não está nos seus dias" in reply
    assert "domingo" in reply


def test_external_coach_only_records_preference():

    runner = make_runner(
        preferred_running_days=["Tuesday", "Sunday"],
        external_coach=True,
    )

    with (
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            PlanPreferenceApplier.apply(
                "renato",
                runner,
                PlanPreference(long_run_day="Sunday"),
            )
        )

    # registra a preferência, mas não gera plano (treinador humano)
    mock_repo.update_fields.assert_called_once()
    mock_provider.for_profile.assert_not_awaited()

    assert "longão" in reply.lower()
