from app.application.history.hr_zone_history import HrZoneHistory
from app.core.clock import today_local
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
        # PLANEJADO × EXECUTADO: guarda a execução bloco-a-bloco (voltas do
        # relógio × passos prescritos) — é de onde o coach calibra os alvos e
        # lê a evolução, vivo. O arquivo reduzido não tem voltas pra recalcular
        # depois. Best-effort; nunca derruba a análise.
        # --------------------------------------------------

        TrainingPipeline._record_execution(profile, coach_context)

        # ESTÍMULO de tiro: guarda o veredito bloco-a-bloco (executou os
        # intervalados no ritmo?) pra o report de aderência ler em lote — o
        # arquivo reduzido não tem splits pra recalcular depois. Best-effort.
        TrainingPipeline._record_stimulus_result(profile, coach_context)

        # --------------------------------------------------
        # Âncora contínua de VDOT (nativa do Garmin): extrai o MELHOR esforço
        # sustentado de dentro deste treino a partir dos streams (distância +
        # tempo) e sobe o teto de capacidade — sem depender do Strava e sem
        # esperar prova. Watermark (só sobe). Best-effort; nunca derruba a
        # análise. Ver [[project_modelo_pace_vdot]].
        # --------------------------------------------------

        TrainingPipeline._record_best_effort(profile, coach_context)

        # --------------------------------------------------
        # Régua VIVA de zonas de FC: a FC muda com a evolução (repouso cai,
        # teto muda) — grava a régua de hoje se mudou, ANTES da IA escrever,
        # pra análise deste treino já poder comentar a mudança. Best-effort.
        # --------------------------------------------------

        HrZoneHistory.record(
            profile,
            runner,
            getattr(coach_context.executed, "hr_zones", None),
            today_local(),
        )

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

            coach_message.positives = ai_analysis.analysis

            coach_message.improvements = []

            # a abertura é o VEREDITO da IA (não o "Parabéns" automático)
            if ai_analysis.headline:

                coach_message.greeting = ai_analysis.headline

            coach_message.attention = (
                [ai_analysis.attention] if ai_analysis.attention else []
            )

            # a leitura da IA SUBSTITUI as frases prontas de histórico/
            # recuperação/fechamento — genéricas ("Excelente consistência",
            # "carga significativa, mas dentro do esperado") e, às vezes,
            # contraditórias com a carga real (diziam "carga bastante elevada"
            # com o ACWR em destreino). Varredura 26/09. O fallback (IA fora)
            # segue com elas.
            coach_message.history = []

            coach_message.recovery = []

            coach_message.closing = ai_analysis.next_step or ""

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

            # o puxão de orelha desta análise (se houve) — o evento registra
            # depois de ENVIAR, pra o coach não repetir a mesma cobrança
            "attention": (
                ai_analysis.attention if ai_analysis else None
            ),

        }

    @staticmethod
    def _record_execution(profile: str, coach_context) -> None:
        """Grava a execução bloco-a-bloco deste treino pro PLANEJADO ×
        EXECUTADO do dossiê. Best-effort — nunca derruba a análise."""

        try:

            from app.application.history.execution_log import (
                entry_from_comparison,
            )
            from app.application.history.training_patterns import (
                TrainingPatterns,
            )
            from app.infrastructure.persistence.execution_log_store import (
                ExecutionLogStore,
            )

            entry = entry_from_comparison(coach_context.block_comparison)

            if entry is None:

                return

            activity = coach_context.executed.activity

            ExecutionLogStore().record(
                profile,
                activity.id,
                TrainingPatterns._local_day(activity.start_date).isoformat(),
                (activity.distance or 0) / 1000,
                entry,
            )

        except Exception as e:

            print(f"Registro de execução falhou p/ '{profile}': {e}")

    @staticmethod
    def _record_stimulus_result(profile: str, coach_context) -> None:
        """Extrai e guarda o veredito de estímulo (tiros no alvo?) deste treino,
        a partir da comparação bloco-a-bloco. Best-effort — nunca derruba a
        análise."""

        try:

            from app.application.history.stimulus_result import (
                stimulus_result_from_comparison,
            )
            from app.infrastructure.persistence.stimulus_result_store import (
                StimulusResultStore,
            )

            result = stimulus_result_from_comparison(
                coach_context.block_comparison
            )

            if result is None:

                return

            activity = coach_context.executed.activity

            StimulusResultStore().record(
                profile,
                activity.id,
                activity.start_date.date().isoformat(),
                result,
            )

        except Exception as e:

            print(f"Registro de estímulo falhou p/ '{profile}': {e}")

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

            from app.application.history.pace_model_builder import gps_broken

            # GPS quebrado (pico sobre-humano) não sobe a marca-d'água
            vdot = (
                None if gps_broken(activity)
                else BestEffortVdot.from_efforts(efforts)
            )

            if vdot is not None:

                BestEffortVdotStore().update(profile, activity.id, vdot)

        except Exception as e:

            print(f"Âncora contínua (Garmin) falhou p/ '{profile}': {e}")
