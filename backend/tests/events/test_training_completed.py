import asyncio
from unittest.mock import AsyncMock, patch

from app.application.events.training_completed import TrainingCompletedEvent
from tests.coach.factories import make_runner

MODULE = "app.application.events.training_completed"


def _run_event(record_message=None, nudge_message=None):

    runner = make_runner(name="Renato")

    result = {
        "runner": runner,
        "message": "análise do treino",
        "history": "history-stub",
        "planned_session": "planned-stub",
        "activity": "activity-stub",
    }

    with (
        patch(f"{MODULE}.TrainingPipeline") as mock_pipeline,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.ProactiveAversionDetector") as mock_aversion,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
    ):

        mock_pipeline.execute = AsyncMock(return_value=result)

        mock_outbox.send = AsyncMock()

        mock_aversion.after_feedback.return_value = nudge_message

        mock_records.after_feedback = AsyncMock(return_value=record_message)

        asyncio.run(
            TrainingCompletedEvent.execute(profile="renato"),
        )

        return runner, result, mock_outbox, mock_records


def test_celebration_message_is_sent_after_analysis():

    runner, result, mock_outbox, mock_records = _run_event(
        record_message="🏆 Renato, sua corrida mais longa!",
    )

    # a fonte dos marcos é o Strava, buscado dentro do próprio detector —
    # não recebe mais history/activity da pipeline (que pode ser Garmin)
    mock_records.after_feedback.assert_awaited_once_with(runner)

    assert mock_outbox.send.await_count == 2

    calls = [c.args for c in mock_outbox.send.await_args_list]
    assert calls[0] == (runner, "análise do treino")
    assert calls[1] == (runner, "🏆 Renato, sua corrida mais longa!")


def test_no_celebration_sends_only_the_analysis():

    runner, _, mock_outbox, mock_records = _run_event(record_message=None)

    mock_records.after_feedback.assert_awaited_once()

    assert mock_outbox.send.await_count == 1


def test_celebration_failure_does_not_break_the_analysis_send():

    runner = make_runner(name="Renato")

    result = {
        "runner": runner,
        "message": "análise do treino",
        "history": "history-stub",
        "planned_session": "planned-stub",
        "activity": "activity-stub",
    }

    with (
        patch(f"{MODULE}.TrainingPipeline") as mock_pipeline,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.ProactiveAversionDetector") as mock_aversion,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
    ):

        mock_pipeline.execute = AsyncMock(return_value=result)
        mock_outbox.send = AsyncMock()
        mock_aversion.after_feedback.return_value = None
        mock_records.after_feedback = AsyncMock(
            side_effect=RuntimeError("boom"),
        )

        asyncio.run(TrainingCompletedEvent.execute(profile="renato"))

        # a análise principal já tinha sido enviada antes do detector quebrar
        assert mock_outbox.send.await_count == 1
