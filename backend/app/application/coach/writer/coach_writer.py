from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.models.coach_message import (
    CoachMessage,
)
from app.application.coach.models.coach_summary import (
    CoachSummary,
)
from app.application.coach.models.next_training import (
    NextTraining,
)
from app.application.coach.signals.finding import (
    Finding,
)
from app.application.coach.writer.phrasebook import (
    ALL_TEMPLATES,
    CLOSING_TEMPLATES,
    GREETING_TEMPLATE,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)


class CoachWriter:

    @staticmethod
    def write(
        context: CoachContext,
        summary: CoachSummary,
    ) -> CoachMessage:

        return CoachMessage(
            greeting=CoachWriter._greeting(summary.runner_name),
            planned_lines=CoachWriter._planned_lines(context.planned),
            executed_lines=CoachWriter._executed_lines(context.executed),
            positives=CoachWriter._render_all(summary.positives),
            improvements=CoachWriter._render_all(summary.improvements),
            history=CoachWriter._render_all(summary.history),
            recovery=CoachWriter._render_all(summary.recovery),
            next_training=CoachWriter._render_next_training(
                summary.next_training,
            ),
            closing=CoachWriter._closing(summary),
        )

    @staticmethod
    def _greeting(
        name: str,
    ) -> str:

        return GREETING_TEMPLATE.format(name=name)

    @staticmethod
    def _planned_lines(
        planned: PlannedSession,
    ) -> list[str]:

        return [
            planned.workout_type,
            f"{(planned.planned_distance_km or 0):.1f} km",
        ]

    @staticmethod
    def _executed_lines(
        executed: EnrichedActivity,
    ) -> list[str]:

        distance = executed.activity.distance / 1000

        return [
            f"{distance:.1f} km",
            f"Ritmo: {executed.pace_min_km:.2f} min/km",
            f"Tipo identificado: {executed.training_type}",
            f"Intensidade: {executed.intensity}",
            f"Zona: {executed.estimated_zone}",
        ]

    @staticmethod
    def _render_all(
        findings: list[Finding],
    ) -> list[str]:

        lines = []

        for finding in findings:

            template = ALL_TEMPLATES.get(finding.code)

            if template is None:

                continue

            lines.append(
                template.format(**finding.params),
            )

        return lines

    @staticmethod
    def _render_next_training(
        next_training: NextTraining | None,
    ) -> list[str]:

        if next_training is None:

            return []

        lines = [
            f"Dia: {next_training.day}",
            f"Tipo: {next_training.workout_type}",
            f"Objetivo: {next_training.objective}",
        ]

        if next_training.distance_km:

            lines.append(
                f"Distância: {next_training.distance_km:.1f} km",
            )

        if next_training.pace != "-":

            lines.append(f"Pace: {next_training.pace}")

        if next_training.notes != "-":

            lines.append(f"Obs: {next_training.notes}")

        return lines

    @staticmethod
    def _closing(
        summary: CoachSummary,
    ) -> str:

        if not summary.recovery:

            return ""

        recovery_finding = summary.recovery[0]

        return CLOSING_TEMPLATES.get(recovery_finding.code, "")
