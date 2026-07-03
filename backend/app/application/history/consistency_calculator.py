from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from app.domain.entities.training_history import TrainingHistory

WeekKey = tuple[int, int]


class ConsistencyCalculator:
    """Adesão ao plano: média de dias treinados vs. dias planejados
    por semana, nas últimas `weeks` semanas COMPLETAS.

    Regras de robustez:
    - A semana em curso fica de fora: na terça-feira ela ainda não
      teve chance de ser cumprida e derrubaria a média injustamente.
    - Semanas anteriores ao primeiro treino do histórico também ficam
      de fora: corredor na 2ª semana não é punido pelas semanas em
      que nem havia começado.
    - Se todo o histórico está na semana em curso (corredor estreante),
      avalia a própria semana em curso.
    """

    @staticmethod
    def calculate(
        history: TrainingHistory,
        weekly_training_days: int,
        weeks: int = 4,
        reference_date: date | None = None,
    ) -> float:

        if weekly_training_days <= 0:

            return 0.0

        if not history.activities:

            return 0.0

        reference_date = reference_date or datetime.now(UTC).date()

        days_by_week: dict[WeekKey, set[date]] = defaultdict(set)

        for activity in history.activities:

            activity_date = activity.start_date.date()

            week_key = activity_date.isocalendar()[:2]

            days_by_week[week_key].add(activity_date)

        # a chave ISO (ano, semana) ordena cronologicamente
        first_week = min(days_by_week)

        # últimas `weeks` semanas completas (exclui a semana em curso),
        # recortadas ao início do histórico
        week_keys = [
            week_key
            for i in range(1, weeks + 1)
            if (
                week_key := (
                    reference_date - timedelta(weeks=i)
                ).isocalendar()[:2]
            )
            >= first_week
        ]

        # corredor estreante: todo o histórico está na semana em curso
        if not week_keys:

            week_keys = [reference_date.isocalendar()[:2]]

        adherence_scores = [
            min(
                len(days_by_week.get(week_key, set()))
                / weekly_training_days,
                1.0,
            )
            for week_key in week_keys
        ]

        return round(
            sum(adherence_scores) / len(adherence_scores) * 100,
            1,
        )
