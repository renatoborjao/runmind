"""Sequência de consistência: quantas semanas SEGUIDAS (mais recentes pra trás)
o atleta cumpriu o plano. Reforço emocional barato ("3 semanas seguidas 🔥").
Puro. NUNCA pune quebra — quando não há sequência, simplesmente não aparece.
Ver [[project_ideias_produto]] item 29 e [[feedback_orientar_nao_mandar]]."""

from app.domain.entities.adherence_report import WeekAdherence

# fração da semana cumprida pra a semana "contar" na sequência
_HIT_THRESHOLD = 0.8


class StreakCalculator:

    @staticmethod
    def consecutive_weeks(
        weeks: list[WeekAdherence],
        threshold: float = _HIT_THRESHOLD,
    ) -> int:
        """Semanas cumpridas em sequência, terminando na mais recente. Semana
        SEM plano (planned=0) não conta nem quebra a sequência — é neutra."""

        streak = 0

        for week in reversed(weeks):

            if week.planned == 0:

                continue

            if week.rate >= threshold:

                streak += 1

            else:

                break

        return streak
