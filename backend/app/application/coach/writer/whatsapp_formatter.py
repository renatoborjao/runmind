from app.application.coach.models.coach_message import (
    CoachMessage,
)
from app.core import messages


class WhatsAppFormatter:

    @staticmethod
    def format(
        message: CoachMessage,
    ) -> str:

        blocks = [
            messages.APP_NAME,
            "",
            message.greeting,
        ]

        blocks += WhatsAppFormatter._section(
            messages.PLANNED_TITLE,
            message.planned_lines,
        )

        blocks += WhatsAppFormatter._section(
            messages.EXECUTED_TITLE,
            message.executed_lines,
        )

        blocks += WhatsAppFormatter._section(
            messages.INTERVALS_TITLE,
            message.interval_lines,
        )

        blocks += WhatsAppFormatter._section(
            messages.SPLITS_TITLE,
            message.splits_lines,
        )

        blocks += WhatsAppFormatter._section(
            messages.ANALYSIS_TITLE,
            message.positives + message.improvements,
        )

        blocks += WhatsAppFormatter._section(
            messages.HISTORY_TITLE,
            message.history,
        )

        blocks += WhatsAppFormatter._section(
            messages.RECOVERY_TITLE,
            message.recovery,
        )

        blocks += WhatsAppFormatter._section(
            messages.NEXT_TRAINING_TITLE,
            message.next_training,
        )

        if message.closing:

            blocks += [
                "",
                messages.NEXT_ACTION.format(message=message.closing),
            ]

        return "\n".join(blocks).strip()

    @staticmethod
    def _section(
        title: str,
        lines: list[str],
    ) -> list[str]:

        if not lines:

            return []

        block = ["", title]

        block += [f"• {line}" for line in lines]

        return block
