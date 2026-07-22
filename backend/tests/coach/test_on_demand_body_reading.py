import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.intent_router import ChatIntent
from app.application.coach.conversation.on_demand_answers import OnDemandAnswers
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.training_load import (
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    TrainingLoad,
)

MODULE = "app.application.coach.conversation.on_demand_answers"


def _reading(load_status, has_recovery):

    return BodyReading(
        load=TrainingLoad(
            acute_load=400,
            chronic_load=240,
            acwr=1.6,
            status=load_status,
            days_of_history=27,
        ),
        recovery=RecoveryTrend(days_covered=10 if has_recovery else 0),
        body_state=BODY_ABSORBING if has_recovery else BODY_BUILDING,
    )


def _answer(reading):

    runner = SimpleNamespace(name="Renato")

    with (
        patch(f"{MODULE}.BodyReadingBuilder.build", return_value=reading),
        patch(
            f"{MODULE}.BodyReadingWriter.write",
            new=AsyncMock(return_value="Seu corpo está absorvendo bem."),
        ),
    ):

        return asyncio.run(
            OnDemandAnswers.answer(ChatIntent.BODY_READING, "renato2", runner)
        )


def test_body_reading_returns_narrative_when_data_exists():

    result = _answer(_reading(LOAD_HIGH, has_recovery=True))

    assert result == "Seu corpo está absorvendo bem."


def test_body_reading_falls_to_gemini_when_no_data():

    # sem recuperação E carga insuficiente -> None (segue no chat/Gemini)
    result = _answer(_reading(LOAD_INSUFFICIENT, has_recovery=False))

    assert result is None
