from app.application.coach.models.coach_message import (
    CoachMessage,
)
from app.application.coach.writer.whatsapp_formatter import (
    WhatsAppFormatter,
)
from app.core import messages


def test_formatter_includes_titles_and_preserves_order():

    message = CoachMessage(
        greeting="Parabéns pelo treino, Renato! 👊",
        planned_lines=["Rodagem Leve", "10.0 km"],
        executed_lines=["10.4 km"],
        positives=["Você respeitou bem o objetivo principal da sessão."],
        improvements=[],
        history=["Boa consistência de treinos."],
        recovery=["Seu organismo respondeu bem ao estímulo."],
        next_training=["Dia: Thursday"],
        closing="Você pode seguir normalmente com o planejamento.",
    )

    text = WhatsAppFormatter.format(message)

    assert text.startswith(messages.APP_NAME)

    assert message.greeting in text

    planned_index = text.index(messages.PLANNED_TITLE)
    executed_index = text.index(messages.EXECUTED_TITLE)
    analysis_index = text.index(messages.ANALYSIS_TITLE)
    history_index = text.index(messages.HISTORY_TITLE)
    recovery_index = text.index(messages.RECOVERY_TITLE)
    next_training_index = text.index(messages.NEXT_TRAINING_TITLE)

    assert (
        planned_index
        < executed_index
        < analysis_index
        < history_index
        < recovery_index
        < next_training_index
    )

    assert "• Rodagem Leve" in text
    assert message.closing in text


def test_formatter_omits_empty_sections():

    message = CoachMessage(
        greeting="Parabéns pelo treino, Renato! 👊",
        planned_lines=["Rodagem Leve", "10.0 km"],
        executed_lines=["10.4 km"],
        positives=[],
        improvements=[],
        history=[],
        recovery=[],
        next_training=[],
        closing="",
    )

    text = WhatsAppFormatter.format(message)

    assert messages.ANALYSIS_TITLE not in text
    assert messages.HISTORY_TITLE not in text
    assert messages.RECOVERY_TITLE not in text
    assert messages.NEXT_TRAINING_TITLE not in text
    assert "\n\n\n" not in text
