from app.application.coach.summary.coach_summary_builder import (
    CoachSummaryBuilder,
)
from app.application.coach.writer.coach_writer import (
    CoachWriter,
)
from app.application.coach.writer.whatsapp_formatter import (
    WhatsAppFormatter,
)
from app.application.orchestrators.coach_analysis_builder import (
    CoachAnalysisBuilder,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)


class LastTrainingReport:
    """Recria, sob demanda, a MESMA análise completa enviada quando o
    treino fecha — sem reajustar nem persistir o plano (é só releitura).

    Diferente do TrainingPipeline, não roda o PlanAdjustmentEngine: pedir
    para rever o último treino não pode mudar o plano da semana."""

    @staticmethod
    async def build(
        profile: str,
    ) -> str | None:

        # Sem treino registrado não há o que reanalisar.
        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        if history.latest is None:

            return None

        result = await CoachAnalysisBuilder.build(
            profile=profile,
        )

        summary = CoachSummaryBuilder.build(
            result["runner"].name,
            result["analysis"],
        )

        message = CoachWriter.write(
            result["context"],
            summary,
        )

        return WhatsAppFormatter.format(message)
