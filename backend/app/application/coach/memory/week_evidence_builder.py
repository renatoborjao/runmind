from datetime import date, timedelta

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.coach.memory.coaching_signal_recorder import (
    CoachingSignalRecorder,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.core.clock import today_local
from app.core.weekdays import weekday_label, weekday_name
from app.domain.entities.adherence_report import (
    ADHERENCE_INSUFFICIENT,
    AdherenceReport,
)
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.checkin_repository import (
    CheckinRepository,
)
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)
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

        # forma aeróbica ao longo do tempo (está evoluindo?) — a RESPOSTA ao
        # estímulo, não só se cumpriu. É o que ensina "responde a X" / "estagna
        # apesar de Y".
        evolution = WeekEvidenceBuilder._evolution(profile, today)

        if evolution:

            parts.append(evolution)

        # o que ELE SENTIU da semana (sRPE dos treinos + check-ins) — o eixo
        # subjetivo que o relógio não mede.
        subjective = WeekEvidenceBuilder._subjective(profile, closing, today)

        if subjective:

            parts.append(subjective)

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

        # persist=False: quem grava o snapshot de domingo é o _send_body_reading
        # (roda antes); aqui só lemos a leitura + a trajetória pro cérebro
        reading, trajectory = BodyReadingService.read(profile, persist=False)

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

        line = "; ".join(parts) + "."

        # a recorrência é o que vira aprendizado durável ("entra em STRAINED
        # quando rampa 2 semanas") — por isso o fato de trajetória entra sempre
        if trajectory.fact:

            line += "\n" + trajectory.fact

        return line

    @staticmethod
    def _evolution(profile, today) -> str:
        """A forma aeróbica ao longo do tempo (o eixo "estou evoluindo?"). É a
        RESPOSTA ao estímulo — o que o cérebro precisa pra aprender o que faz o
        atleta melhorar ou estagnar, além de só cumprir/furar. Só entra com
        lastro E fresco (não `stale`): forma velha não é a de agora. Best-effort
        — falha aqui não derruba o resto da evidência."""

        try:

            evo = FitnessReadingService.read_evolution(
                profile, reference_date=today,
            )

        except Exception:

            return ""

        if not evo.has_data or evo.stale:

            return ""

        parts = [
            "Forma aeróbica ao longo do tempo (está evoluindo?): "
            f"{evo.direction} ({evo.confidence})"
        ]

        ef = evo.ef

        if ef and ef.has_data and ef.pace_gain_sec is not None:

            prefix = "mais de " if ef.pace_gain_capped else ""

            parts.append(
                f"economia na rodagem: {prefix}{ef.pace_gain_sec} s/km mais "
                f"rápido na mesma FC ({ef.runs_counted} corridas)"
            )

        if evo.quality is not None:

            parts.append(f"em ritmo forte: {evo.quality.direction}")

        if evo.vo2max is not None:

            parts.append(f"VO₂máx da Garmin: {evo.vo2max.direction}")

        if evo.rhr is not None:

            parts.append(f"FC-repouso: {evo.rhr.direction}")

        return "; ".join(parts) + "."

    @staticmethod
    def _subjective(profile, closing, today) -> str:
        """O que ELE SENTIU da semana: sRPE dos treinos (esforço percebido) +
        check-ins de sensação. Ensina traço durável — percebe esforço acima ou
        abaixo do que a FC mede, tolera ou não tal carga. Só a semana FECHADA.
        Best-effort."""

        if closing is None:

            return ""

        try:

            window = WeekEvidenceBuilder._week_window(closing)

            lines = (
                WeekEvidenceBuilder._srpe_lines(profile, window)
                + WeekEvidenceBuilder._checkin_lines(profile, window)
            )

        except Exception:

            return ""

        if not lines:

            return ""

        return "Como ELE sentiu a semana (subjetivo):\n" + "\n".join(lines)

    @staticmethod
    def _week_window(closing) -> tuple[date, date]:

        start = closing.week_start

        return start, start + timedelta(days=6)

    @staticmethod
    def _in_window(day_iso: str, window: tuple[date, date]) -> bool:

        try:

            day = date.fromisoformat(day_iso)

        except (ValueError, TypeError):

            return False

        return window[0] <= day <= window[1]

    @staticmethod
    def _srpe_lines(profile, window) -> list[str]:

        sessions = SessionRpeRepository().load_sessions(profile)

        lines = []

        for s in sorted(sessions, key=lambda x: x.day):

            if not WeekEvidenceBuilder._in_window(s.day, window):

                continue

            label = weekday_label(weekday_name(date.fromisoformat(s.day)))

            lines.append(
                f"- {label}: esforço percebido RPE {s.rpe}/10 "
                f"(sRPE {s.srpe:.0f})"
            )

        return lines

    @staticmethod
    def _checkin_lines(profile, window) -> list[str]:

        checkins = CheckinRepository().load(profile)

        lines = []

        for c in sorted(checkins, key=lambda x: x.day):

            if not c.has_data or not WeekEvidenceBuilder._in_window(
                c.day, window,
            ):

                continue

            label = weekday_label(weekday_name(date.fromisoformat(c.day)))

            bits = []

            if c.energy is not None:

                bits.append(f"energia {c.energy}/5")

            if c.sleep_quality is not None:

                bits.append(f"sono {c.sleep_quality}/5")

            if c.soreness is not None:

                bits.append(f"dor {c.soreness}/5")

            if c.note:

                bits.append(c.note)

            lines.append(f"- {label}: relatou {', '.join(bits)}")

        return lines
