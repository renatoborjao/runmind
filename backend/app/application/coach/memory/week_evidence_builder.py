from datetime import timedelta

from app.application.coach.intelligence.body_reading_builder import (
    BodyReadingBuilder,
)
from app.application.coach.memory.coaching_signal_recorder import (
    CoachingSignalRecorder,
)
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.core.clock import today_local
from app.core.weekdays import weekday_label
from app.domain.entities.adherence_report import (
    ADHERENCE_INSUFFICIENT,
    AdherenceReport,
)
from app.domain.entities.body_reading import BodyReading
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WeekEvidenceBuilder:
    """Monta, em texto, a evidência da semana que fechou — o insumo que a
    destilação de domingo (CoachLearningEngine) lê pra aprender. Costura as
    três fontes: prescrito×executado (B), correções aceitas (A) e resposta
    fisiológica (C). Só fatos; string vazia quando não há nada a aprender."""

    @staticmethod
    def build(
        profile: str,
        history: TrainingHistory,
    ) -> str:

        today = today_local()

        plans = WeeklyPlanRepository().history(profile)

        # a última semana FECHADA (domingo <= hoje). NUNCA a semana em curso —
        # senão as sessões que ainda não venceram (ex.: longão de domingo numa
        # sexta) apareceriam como furadas. No domingo 20h, a semana que fecha
        # HOJE já conta (Sunday == hoje).
        closing = WeekEvidenceBuilder._closing_plan(plans, today)

        closing_week = closing.week_start if closing else None

        parts = []

        executed = WeekEvidenceBuilder._executed(closing, history, today)

        if executed:

            parts.append(executed)

        adherence = WeekEvidenceBuilder._adherence(
            plans, history, closing_week, today,
        )

        if adherence:

            parts.append(adherence)

        corrections = WeekEvidenceBuilder._corrections(profile)

        if corrections:

            parts.append(corrections)

        body = WeekEvidenceBuilder._body(profile)

        if body:

            parts.append(body)

        # contexto de vida (viagem/lesão/agenda que o atleta CONTOU) — pra a
        # destilação não transformar um furo pontual e explicado (ex.: viagem)
        # num "padrão" durável. É a mesma memória evolutiva do chat.
        context = RunnerMemoryService.render(profile)

        if context:

            parts.append(
                "Contexto de vida que ele já contou (pode explicar furos "
                "pontuais — NÃO vire padrão a partir disto):\n" + context
            )

        return "\n\n".join(parts)

    @staticmethod
    def _closing_plan(plans, today):
        """O plano da última semana FECHADA: a mais recente cujo domingo
        (week_start + 6) já chegou em relação a hoje. Exclui a semana em
        curso, cujas sessões ainda não venceram."""

        closed = [
            p
            for p in plans
            if p.week_start + timedelta(days=6) <= today
        ]

        return max(closed, key=lambda p: p.week_start) if closed else None

    @staticmethod
    def _executed(closing, history, today) -> str:

        # ExecutedWeekSummary casa cada atividade com a sessão planejada;
        # reference_date blinda sessão que ainda não venceu
        return ExecutedWeekSummary.build(
            closing, history.activities, reference_date=today,
        )

    @staticmethod
    def _adherence(plans, history, closing_week, today) -> str:

        if closing_week is None:

            return ""

        report: AdherenceReport = AdherenceAnalyzer.analyze(
            plans,
            history,
            until_week=closing_week,
            reference_date=today,
        )

        if report.trend == ADHERENCE_INSUFFICIENT and not report.weeks:

            return ""

        lines = []

        if report.weeks:

            series = ", ".join(
                f"{w.done}/{w.planned}" for w in report.weeks
            )

            lines.append(
                f"Aderência semana a semana (feito/planejado): {series} "
                f"(tendência {report.trend})."
            )

        if report.missed_day:

            lines.append(
                "Mais fura no dia %s (%d de %d vezes que foi prescrito)."
                % (
                    weekday_label(report.missed_day.label),
                    report.missed_day.count,
                    report.missed_day.opportunities,
                )
            )

        if report.missed_type:

            lines.append(
                "Mais fura o treino de %s (%d de %d)."
                % (
                    report.missed_type.label,
                    report.missed_type.count,
                    report.missed_type.opportunities,
                )
            )

        return "\n".join(lines)

    @staticmethod
    def _corrections(profile) -> str:

        signals = CoachingSignalRecorder.load(profile)

        if not signals:

            return ""

        lines = ["Correções que ELE pediu/aceitou nesta semana:"]

        for signal in signals:

            lines.append(
                f"- {signal.get('kind', '?')}: {signal.get('detail', '')}"
            )

        return "\n".join(lines)

    @staticmethod
    def _body(profile) -> str:

        reading: BodyReading = BodyReadingBuilder.build(profile)

        if not reading.recovery.has_data:

            return ""

        parts = [f"Corpo (carga à luz da recuperação): estado {reading.body_state}"]

        if reading.limiter:

            parts.append(f"limitador: {reading.limiter}")

        rec = reading.recovery

        if rec.hrv_recent is not None:

            parts.append(f"HRV {rec.hrv_recent:.0f} ({rec.hrv_direction})")

        if rec.short_nights and rec.nights_counted:

            parts.append(
                f"{rec.short_nights} de {rec.nights_counted} noites < 6h"
            )

        if reading.load.acwr is not None:

            parts.append(f"ACWR {reading.load.acwr:.2f}")

        return "; ".join(parts) + "."
