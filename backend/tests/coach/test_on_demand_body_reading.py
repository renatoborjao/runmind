import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
        patch(
            f"{MODULE}.BodyReadingService.read",
            return_value=(reading, MagicMock()),
        ),
        patch(
            f"{MODULE}.BodyReadingService.narrative_for",
            new=AsyncMock(return_value=None),
        ),
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

    assert result.startswith("Seu corpo está absorvendo bem.")
    # ponte pro eixo irmão (forma), pra corpo e forma não parecerem se anular
    assert "como tá minha forma" in result


def test_chat_reuses_the_apps_reading_of_the_night():
    """Perguntar no chat não chama a IA de novo: é a mesma leitura do app."""

    write = AsyncMock(return_value="nova")

    with (
        patch(
            f"{MODULE}.BodyReadingService.read",
            return_value=(_reading(LOAD_HIGH, has_recovery=True), MagicMock()),
        ),
        patch(
            f"{MODULE}.BodyReadingService.narrative_for",
            new=AsyncMock(return_value="🩺 A do app"),
        ),
        patch(f"{MODULE}.BodyReadingWriter.write", new=write),
    ):

        result = asyncio.run(
            OnDemandAnswers.answer(
                ChatIntent.BODY_READING, "renato2", SimpleNamespace(name="Renato"),
            )
        )

    assert result.startswith("🩺 A do app")
    write.assert_not_called()


def test_body_reading_falls_to_gemini_when_no_data():

    # sem recuperação E carga insuficiente -> None (segue no chat/Gemini)
    result = _answer(_reading(LOAD_INSUFFICIENT, has_recovery=False))

    assert result is None
