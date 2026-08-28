import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.events.training_completed import TrainingCompletedEvent
from tests.coach.factories import make_runner

MODULE = "app.application.events.training_completed"


def _shoe_outcome(label="Boston", wear_alert=None):

    return SimpleNamespace(
        shoe=SimpleNamespace(label=label), wear_alert=wear_alert,
    )


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


def test_race_day_suppresses_generic_feedback_and_sends_debrief():
    """Na prova-alvo o feedback de treino comum ("análise do treino") NÃO sai,
    nem o detector de aversão — quem conduz é o debrief de prova. Era a queixa
    do Renato: a prova tratada como "mais um treino"."""

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
        patch(f"{MODULE}.RaceDebrief") as mock_race,
    ):

        mock_pipeline.execute = AsyncMock(return_value=result)
        mock_outbox.send = AsyncMock()
        mock_records.after_feedback = AsyncMock(return_value=None)
        mock_race.is_target_race.return_value = True
        mock_race.after_feedback = AsyncMock(return_value="🏁 VOCÊ CONSEGUIU")

        asyncio.run(TrainingCompletedEvent.execute(profile="renato"))

    sent = [c.args[1] for c in mock_outbox.send.await_args_list]
    kinds = [c.kwargs.get("kind") for c in mock_outbox.send.await_args_list]

    # o feedback genérico foi CALADO; só o debrief de prova saiu
    assert "análise do treino" not in sent
    assert "feedback" not in kinds
    assert "🏁 VOCÊ CONSEGUIU" in sent
    assert "race_debrief" in kinds
    # numa prova não se pergunta aversão
    mock_aversion.after_feedback.assert_not_called()


def test_shoe_note_is_appended_to_feedback():
    """A nota passiva "contei essa no teu X" vai na MESMA mensagem do feedback."""

    runner = make_runner(name="Renato")

    result = {
        "runner": runner, "message": "análise do treino",
        "history": "h", "planned_session": "p", "activity": "a",
    }

    with (
        patch(f"{MODULE}.TrainingPipeline") as mock_pipeline,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.ProactiveAversionDetector") as mock_aversion,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
        patch.object(TrainingCompletedEvent, "_attribute_shoe",
                     return_value=_shoe_outcome(label="Vaporfly")),
    ):

        mock_pipeline.execute = AsyncMock(return_value=result)
        mock_outbox.send = AsyncMock()
        mock_aversion.after_feedback.return_value = None
        mock_records.after_feedback = AsyncMock(return_value=None)

        asyncio.run(TrainingCompletedEvent.execute(profile="renato"))

    feedback = mock_outbox.send.await_args_list[0].args[1]
    assert "análise do treino" in feedback
    assert "Vaporfly" in feedback and "Contei essa" in feedback


def test_wear_alert_sent_as_own_message():

    runner = make_runner(name="Renato")

    result = {
        "runner": runner, "message": "análise do treino",
        "history": "h", "planned_session": "p", "activity": "a",
    }

    with (
        patch(f"{MODULE}.TrainingPipeline") as mock_pipeline,
        patch(f"{MODULE}.CoachOutbox") as mock_outbox,
        patch(f"{MODULE}.ProactiveAversionDetector") as mock_aversion,
        patch(f"{MODULE}.PersonalRecordDetector") as mock_records,
        patch.object(TrainingCompletedEvent, "_attribute_shoe",
                     return_value=_shoe_outcome(wear_alert="⚠️ tênis gasto")),
    ):

        mock_pipeline.execute = AsyncMock(return_value=result)
        mock_outbox.send = AsyncMock()
        mock_aversion.after_feedback.return_value = None
        mock_records.after_feedback = AsyncMock(return_value=None)

        asyncio.run(TrainingCompletedEvent.execute(profile="renato"))

    sent = [c.args[1] for c in mock_outbox.send.await_args_list]
    kinds = [c.kwargs.get("kind") for c in mock_outbox.send.await_args_list]
    assert "⚠️ tênis gasto" in sent
    assert "shoe_wear" in kinds


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
