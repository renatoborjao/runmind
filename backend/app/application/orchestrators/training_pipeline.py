from app.application.coach.planning.plan_adjustment_engine import (
    PlanAdjustmentEngine,
)
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
from app.domain.entities.activity import (
    Activity,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class TrainingPipeline:

    @staticmethod
    async def execute(
        profile: str = "renato",
        activity: Activity | None = None,
    ):

        # --------------------------------------------------
        # Análise (read-only, compartilhada com a API)
        # --------------------------------------------------

        result = await CoachAnalysisBuilder.build(
            profile=profile,
            activity=activity,
        )

        runner = result["runner"]

        plan = result["plan"]

        planned_session = result["planned_session"]

        coach_context = result["context"]

        coach_analysis = result["analysis"]

        # --------------------------------------------------
        # Mensagem do coach
        # --------------------------------------------------

        coach_summary = CoachSummaryBuilder.build(
            runner.name,
            coach_analysis,
        )

        coach_message = CoachWriter.write(
            coach_context,
            coach_summary,
        )

        # --------------------------------------------------
        # Ajuste do plano (determinístico, com base na análise acima)
        # Treino extra (sem sessão planejada) não ajusta o plano.
        # --------------------------------------------------

        adjustment_note = None

        if planned_session is not None:

            adjustment_note = PlanAdjustmentEngine.adjust(
                plan,
                planned_session,
                coach_analysis,
            )

        if adjustment_note:

            WeeklyPlanRepository().save(
                profile,
                plan,
            )

        # --------------------------------------------------
        # Mensagem
        # --------------------------------------------------

        message = WhatsAppFormatter.format(
            coach_message,
        )

        if adjustment_note:

            message = (
                f"{message}\n\n📅 {adjustment_note}"
            )

        # --------------------------------------------------
        # Resultado
        # --------------------------------------------------

        return {

            "runner": runner,

            "history": result["history"],

            "assessment": result["assessment"],

            "plan": plan,

            "planned_session": planned_session,

            "activity": result["enriched"],

            "coach_analysis": coach_analysis,

            "coach_summary": coach_summary,

            "message": message,

        }
