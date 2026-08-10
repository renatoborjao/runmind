from app.application.coach.planning.plan_adjustment_engine import (
    PlanAdjustmentEngine,
)
from app.application.coach.summary.coach_summary_builder import (
    CoachSummaryBuilder,
)
from app.application.coach.writer.ai_analysis_writer import (
    AIAnalysisWriter,
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
        profile: str,
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
        # Auto-calibração: registra o ERRO de previsão de pace (prescrito ×
        # sustentado nos tiros) desta atividade — o coach mede o próprio erro
        # pra ajustar o alvo ao que o atleta aguenta. Best-effort, dedup por
        # atividade; nunca derruba a análise.
        # --------------------------------------------------

        TrainingPipeline._record_pace_calibration(profile, coach_context)

        # --------------------------------------------------
        # Âncora contínua de VDOT (nativa do Garmin): extrai o MELHOR esforço
        # sustentado de dentro deste treino a partir dos streams (distância +
        # tempo) e sobe o teto de capacidade — sem depender do Strava e sem
        # esperar prova. Watermark (só sobe). Best-effort; nunca derruba a
        # análise. Ver [[project_modelo_pace_vdot]].
        # --------------------------------------------------

        TrainingPipeline._record_best_effort(profile, coach_context)

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
        # Análise pela IA-treinadora: escreve a seção "📊 Análise"
        # ancorada nos fatos + na estrutura real do treino (splits).
        # Se a IA falhar, mantém a análise determinística (fallback).
        # --------------------------------------------------

        ai_analysis = await AIAnalysisWriter.write(coach_context)

        if ai_analysis:

            coach_message.positives = ai_analysis

            coach_message.improvements = []

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

    @staticmethod
    def _record_pace_calibration(profile: str, coach_context) -> None:
        """Extrai o erro de pace dos tiros deste treino e guarda pra
        auto-calibração. Best-effort — nunca derruba a análise."""

        try:

            comparison = coach_context.block_comparison

            if comparison is None:

                return

            from app.application.history.pace_calibration_analyzer import (
                PaceCalibrationAnalyzer,
            )
            from app.infrastructure.persistence.pace_calibration_store import (
                PaceCalibrationStore,
            )

            deltas = PaceCalibrationAnalyzer.deltas_from_blocks(
                comparison.blocks
            )

            if deltas:

                PaceCalibrationStore().record(
                    profile,
                    coach_context.executed.activity.id,
                    deltas,
                )

        except Exception as e:

            print(f"Calibração de pace falhou p/ '{profile}': {e}")

    @staticmethod
    def _record_best_effort(profile: str, coach_context) -> None:
        """Extrai o melhor esforço CONTÍNUO deste treino (streams do Garmin) e
        sobe a marca-d'água do VDOT contínuo. Só age quando há stream de
        distância+tempo (caminho Garmin); o Strava segue pelo BestEffortRefresh
        de domingo. Best-effort — nunca derruba a análise."""

        try:

            activity = coach_context.executed.activity

            streams = (getattr(activity, "raw", None) or {}).get("_streams") or {}

            distance = streams.get("distance") or []

            time = streams.get("time") or []

            if not distance or not time:

                return

            from app.application.history.best_effort_extractor import (
                BestEffortExtractor,
            )
            from app.application.history.best_effort_vdot import BestEffortVdot
            from app.infrastructure.persistence.best_effort_vdot_store import (
                BestEffortVdotStore,
            )

            efforts = BestEffortExtractor.efforts(distance, time)

            vdot = BestEffortVdot.from_efforts(efforts)

            if vdot is not None:

                BestEffortVdotStore().update(profile, activity.id, vdot)

        except Exception as e:

            print(f"Âncora contínua (Garmin) falhou p/ '{profile}': {e}")
