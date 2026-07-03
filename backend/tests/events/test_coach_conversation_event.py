import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.events.coach_conversation import (
    CoachConversationEvent,
)
from tests.coach.factories import make_runner

MODULE = "app.application.events.coach_conversation"


def _run_event(
    extraction_ops=None,
    extraction_error=None,
):

    runner = make_runner(name="Renato", phone="+5511975658679")

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.ConversationContextBuilder") as mock_context_builder,
        patch(f"{MODULE}.ConversationRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEngine") as mock_engine,
        patch(f"{MODULE}.NotificationService") as mock_notification,
        patch(f"{MODULE}.RunnerMemoryRepository") as mock_memory_repo_cls,
        patch(f"{MODULE}.MemoryExtractionEngine") as mock_extraction,
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory_service,
    ):

        mock_load_runner.execute.return_value = runner

        mock_context_builder.build = AsyncMock(
            return_value="Volume semanal atual: 30.0 km",
        )

        mock_repo = MagicMock()
        mock_repo.recent_turns.return_value = [
            {"role": "user", "text": "oi"},
        ]
        mock_repo_cls.return_value = mock_repo

        mock_engine.reply = AsyncMock(
            return_value="Bom dia! Foi um baita treino ontem.",
        )

        mock_notification.send_training_feedback = AsyncMock()

        mock_memory_repo_cls.return_value.active.return_value = []

        if extraction_error is not None:
            mock_extraction.extract = AsyncMock(
                side_effect=extraction_error,
            )
        else:
            mock_extraction.extract = AsyncMock(
                return_value=extraction_ops
                or {"add": [], "archive": []},
            )

        reply = asyncio.run(
            CoachConversationEvent.execute(
                profile="renato",
                incoming_text="Como foi meu treino de ontem?",
                sender_name="Renato",
            )
        )

        return (
            reply,
            mock_load_runner,
            mock_context_builder,
            mock_repo,
            mock_engine,
            mock_notification,
            mock_extraction,
            mock_memory_service,
        )


def test_execute_orchestrates_context_reply_persistence_and_notification():

    (
        reply,
        mock_load_runner,
        mock_context_builder,
        mock_repo,
        mock_engine,
        mock_notification,
        _,
        _,
    ) = _run_event()

    assert reply == "Bom dia! Foi um baita treino ontem."

    mock_load_runner.execute.assert_called_once_with("renato")

    mock_context_builder.build.assert_awaited_once_with("renato")

    mock_engine.reply.assert_awaited_once_with(
        runner_name="Renato",
        context_facts="Volume semanal atual: 30.0 km",
        conversation_history=[{"role": "user", "text": "oi"}],
        incoming_text="Como foi meu treino de ontem?",
    )

    assert mock_repo.append_turn.call_count == 2

    mock_repo.append_turn.assert_any_call(
        "renato",
        role="user",
        text="Como foi meu treino de ontem?",
    )

    mock_repo.append_turn.assert_any_call(
        "renato",
        role="assistant",
        text="Bom dia! Foi um baita treino ontem.",
    )

    mock_notification.send_training_feedback.assert_awaited_once_with(
        phone="+5511975658679",
        message="Bom dia! Foi um baita treino ontem.",
    )


def test_memory_ops_are_applied_after_reply():

    (
        reply,
        *_,
        mock_extraction,
        mock_memory_service,
    ) = _run_event(
        extraction_ops={
            "add": [{"category": "lesao", "content": "Dor no joelho"}],
            "archive": [],
        },
    )

    assert reply == "Bom dia! Foi um baita treino ontem."

    mock_extraction.extract.assert_awaited_once()

    mock_memory_service.process.assert_called_once_with(
        "renato",
        {
            "add": [{"category": "lesao", "content": "Dor no joelho"}],
            "archive": [],
        },
    )


def test_memory_is_not_touched_when_no_ops():

    (
        _,
        *_,
        mock_extraction,
        mock_memory_service,
    ) = _run_event(
        extraction_ops={"add": [], "archive": []},
    )

    mock_extraction.extract.assert_awaited_once()

    mock_memory_service.process.assert_not_called()


def _turns(count: int, start: int = 0) -> list[dict]:

    return [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "text": f"turno {i}",
            "timestamp": f"2026-07-03T10:{i:02d}:00+00:00",
        }
        for i in range(start, start + count)
    ]


def _run_summary_check(total_turns, covered_until=""):

    with (
        patch(f"{MODULE}.ConversationSummaryEngine") as mock_engine,
    ):

        mock_engine.summarize = AsyncMock(
            return_value="resumo atualizado",
        )

        repo = MagicMock()
        repo.load.return_value = _turns(total_turns)
        repo.load_summary.return_value = {
            "summary": "resumo antigo",
            "covered_until": covered_until,
        }

        asyncio.run(
            CoachConversationEvent._update_summary(
                profile="renato",
                runner_name="Renato",
                repo=repo,
            )
        )

        return mock_engine, repo


def test_summary_folds_when_enough_turns_left_the_window():

    # 32 turnos: 12 fora da janela de 20 (>= lote mínimo de 10)
    mock_engine, repo = _run_summary_check(total_turns=32)

    mock_engine.summarize.assert_awaited_once()

    kwargs = mock_engine.summarize.await_args.kwargs
    assert len(kwargs["turns"]) == 12
    assert kwargs["current_summary"] == "resumo antigo"

    repo.save_summary.assert_called_once_with(
        "renato",
        "resumo atualizado",
        "2026-07-03T10:11:00+00:00",  # último turno dobrado
    )


def test_summary_does_not_fold_below_batch_minimum():

    # 25 turnos: só 5 fora da janela (< 10)
    mock_engine, repo = _run_summary_check(total_turns=25)

    mock_engine.summarize.assert_not_awaited()
    repo.save_summary.assert_not_called()


def test_summary_skips_turns_already_covered():

    # 40 turnos, mas os 15 primeiros já cobertos -> só 5 pendentes
    mock_engine, repo = _run_summary_check(
        total_turns=40,
        covered_until="2026-07-03T10:14:00+00:00",
    )

    mock_engine.summarize.assert_not_awaited()


def test_gemini_failure_sends_busy_reply_instead_of_silence():

    runner = make_runner(name="Renato", phone="+5511975658679")

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.ConversationContextBuilder") as mock_context,
        patch(f"{MODULE}.ConversationRepository") as mock_repo_cls,
        patch(f"{MODULE}.CoachConversationEngine") as mock_engine,
        patch(f"{MODULE}.NotificationService") as mock_notification,
        patch(f"{MODULE}.RunnerMemoryRepository") as mock_memory_repo,
        patch(f"{MODULE}.MemoryExtractionEngine") as mock_extraction,
        patch(f"{MODULE}.RunnerMemoryService"),
    ):

        mock_load_runner.execute.return_value = runner

        mock_context.build = AsyncMock(return_value="fatos")

        mock_repo = MagicMock()
        mock_repo.recent_turns.return_value = []
        mock_repo_cls.return_value = mock_repo

        mock_engine.reply = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"),
        )

        mock_notification.send_training_feedback = AsyncMock()

        mock_memory_repo.return_value.active.return_value = []
        mock_extraction.extract = AsyncMock(
            return_value={"add": [], "archive": []},
        )

        reply = asyncio.run(
            CoachConversationEvent.execute(
                profile="renato",
                incoming_text="qual meu treino de amanhã?",
            )
        )

        # o atleta recebe resposta, não silêncio/500
        assert "me embananei" in reply.lower() or "de novo" in reply

        mock_notification.send_training_feedback.assert_awaited_once()


def test_extraction_failure_does_not_break_reply():

    (
        reply,
        *_,
        mock_notification,
        mock_extraction,
        mock_memory_service,
    ) = _run_event(
        extraction_error=RuntimeError("Gemini fora do ar"),
    )

    assert reply == "Bom dia! Foi um baita treino ontem."

    mock_notification.send_training_feedback.assert_awaited_once()

    mock_memory_service.process.assert_not_called()
