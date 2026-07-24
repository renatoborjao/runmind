"""Aderência ao plano ao LONGO DO TEMPO. O resumo semanal já conta quantos
treinos da semana saíram; aqui a pergunta é outra: o atleta vem cumprindo
mais ou menos? E, principalmente, O QUE ele vive furando — a quinta-feira?
o intervalado?

Esse padrão é o que muda comportamento: em vez de represcrever eternamente
um treino que nunca acontece, o coach pode reposicionar o dia/tipo. Os dados
já estavam no disco (storage/plans/history) e ninguém lia.

Puro/testável, sem IO — recebe os planos já carregados. Não fala com o
atleta e não decide nada sozinho. Honestidade: padrão só é afirmado quando
REPETE (furar uma vez é vida, não padrão)."""

from collections import Counter
from datetime import date, timedelta

from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.clock import today_local
from app.domain.entities.adherence_report import (
    ADHERENCE_FALLING,
    ADHERENCE_INSUFFICIENT,
    ADHERENCE_RISING,
    ADHERENCE_STABLE,
    AdherenceReport,
    MissedPattern,
    WeekAdherence,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan

# o plano é só de corrida/caminhada (mesmo filtro do resumo semanal)
_RUNNING_KINDS = {"run", "walk", "run_walk"}

LOOKBACK_WEEKS = 8

# padrão precisa de repetição E de recorrência: 2+ furos, em pelo menos
# metade das vezes que aquele dia/tipo foi prescrito. Sem isso, uma quinta
# perdida numa semana de viagem viraria "você sempre fura a quinta".
_MIN_OCCURRENCES = 2
_MIN_MISS_RATIO = 0.5

# tendência só com 4+ semanas (duas de cada lado); menos que isso, a metade
# recente é uma semana só e qualquer viagem vira "caindo"
_MIN_WEEKS_FOR_TREND = 4

# folga pra "estável" — variação menor que isso é ruído de rotina
_TREND_TOLERANCE = 0.15


class AdherenceAnalyzer:

    @staticmethod
    def analyze(
        plans: list[TrainingPlan],
        history: TrainingHistory,
        until_week: date,
        weeks: int = LOOKBACK_WEEKS,
        reference_date: date | None = None,
    ) -> AdherenceReport:
        """Série de aderência das últimas `weeks` semanas ATÉ `until_week`
        (inclusive), mais tendência e padrão de furo.

        `until_week` é a segunda-feira da última semana que deve entrar —
        quem chama decide: o resumo de domingo passa a semana que está
        fechando; o gerador de plano passa a semana anterior à que vai
        montar (a nova ainda não aconteceu)."""

        today = reference_date or today_local()

        window = AdherenceAnalyzer._plans_in_window(plans, until_week, weeks)

        series = [
            AdherenceAnalyzer._week(plan, history, today)
            for plan in window
        ]

        series = [week for week in series if week is not None]

        if not series:

            return AdherenceReport()

        planned_total = sum(week.planned for week in series)

        done_total = sum(week.done for week in series)

        return AdherenceReport(
            weeks=series,
            rate=(
                round(done_total / planned_total, 2)
                if planned_total
                else None
            ),
            trend=AdherenceAnalyzer._trend(series),
            missed_day=AdherenceAnalyzer._pattern(
                window,
                series,
                today,
                by_day=True,
            ),
            missed_type=AdherenceAnalyzer._pattern(
                window,
                series,
                today,
                by_day=False,
            ),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _plans_in_window(
        plans: list[TrainingPlan],
        until_week: date,
        weeks: int,
    ) -> list[TrainingPlan]:
        """Planos da janela, cronológicos e sem semana repetida. O histórico
        pode ter a MESMA semana mais de uma vez (regerar o plano com
        force=True acrescenta outra linha) — vale o último gravado, que é o
        plano que o atleta de fato recebeu."""

        first_week = until_week - timedelta(days=7 * (weeks - 1))

        by_week: dict[date, TrainingPlan] = {}

        for plan in plans:

            if first_week <= plan.week_start <= until_week:

                by_week[plan.week_start] = plan

        return [by_week[week] for week in sorted(by_week)]

    @staticmethod
    def _week(
        plan: TrainingPlan,
        history: TrainingHistory,
        today: date,
    ) -> WeekAdherence | None:
        """Uma semana do plano confrontada com o que foi treinado de verdade.
        None quando não há sessão de corrida VENCIDA pra cobrar (semana só de
        descanso, plano vazio, ou semana ainda em curso)."""

        running = [
            session
            for session in plan.sessions
            if session.kind in _RUNNING_KINDS
            and plan.session_date(session) <= today
        ]

        if not running:

            return None

        fulfilled = WeeklyPlanMatcher.fulfilled_days(
            plan,
            history.activities,
        )

        missed = [
            session for session in running if session.day not in fulfilled
        ]

        return WeekAdherence(
            week_start=plan.week_start,
            planned=len(running),
            done=len(running) - len(missed),
            missed_days=[session.day for session in missed],
            missed_types=[
                session.workout_type
                for session in missed
                if session.workout_type
            ],
        )

    @staticmethod
    def _trend(series: list[WeekAdherence]) -> str:
        """Metade recente vs metade antiga da série."""

        if len(series) < _MIN_WEEKS_FOR_TREND:

            return ADHERENCE_INSUFFICIENT

        half = len(series) // 2

        older = series[:half]

        recent = series[len(series) - half:]

        delta = AdherenceAnalyzer._mean_rate(
            recent
        ) - AdherenceAnalyzer._mean_rate(older)

        if delta > _TREND_TOLERANCE:

            return ADHERENCE_RISING

        if delta < -_TREND_TOLERANCE:

            return ADHERENCE_FALLING

        return ADHERENCE_STABLE

    @staticmethod
    def _mean_rate(series: list[WeekAdherence]) -> float:

        return sum(week.rate for week in series) / len(series)

    @staticmethod
    def _pattern(
        plans: list[TrainingPlan],
        series: list[WeekAdherence],
        today: date,
        by_day: bool,
    ) -> MissedPattern | None:
        """O dia (ou tipo) que mais fica pra trás, medido contra quantas
        vezes ele foi PRESCRITO — furar 3 de 3 quintas é um padrão; furar 3
        de 8 é uma rotina que funciona na maior parte do tempo."""

        missed = Counter()

        for week in series:

            missed.update(week.missed_days if by_day else week.missed_types)

        if not missed:

            return None

        prescribed = Counter()

        for plan in plans:

            for session in plan.sessions:

                if (
                    session.kind not in _RUNNING_KINDS
                    or plan.session_date(session) > today
                ):

                    continue

                label = session.day if by_day else session.workout_type

                if label:

                    prescribed[label] += 1

        label, count = missed.most_common(1)[0]

        opportunities = prescribed.get(label, count)

        if count < _MIN_OCCURRENCES:

            return None

        if count / opportunities < _MIN_MISS_RATIO:

            return None

        return MissedPattern(
            label=label,
            count=count,
            opportunities=opportunities,
        )
