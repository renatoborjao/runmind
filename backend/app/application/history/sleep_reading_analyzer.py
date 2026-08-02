"""O sono lido como eixo próprio: média, tendência, regularidade e dívida a
partir da série diária de saúde do Garmin. Puro/testável — espelha o
RecoveryTrendAnalyzer, mas focado só no sono. Ver [[project_analise_corpo_garmin]]."""

import statistics
from datetime import date

from app.domain.entities.body_reading import FALLING, RISING, STABLE
from app.domain.entities.daily_health import DailyHealth
from app.domain.entities.sleep_reading import (
    HEALTHY_FLOOR_HOURS,
    SleepReading,
)

# janela de dias (o comportamento recente, não a vida toda)
_WINDOW_DAYS = 14

# mínimo de noites pra arriscar uma direção/regularidade (senão fica neutro)
_MIN_POINTS = 4

# folga (h) pra chamar a tendência de "mudou" — ruído natural do sono
_HOURS_DELTA = 0.4

# desvio-padrão (h) acima do qual o sono é "irregular" (varia muito noite a noite)
_IRREGULAR_STDEV = 1.0


class SleepReadingAnalyzer:

    @staticmethod
    def analyze(
        series: list[DailyHealth],
        reference_date: date | None = None,
    ) -> SleepReading:
        """Leitura de sono dos últimos _WINDOW_DAYS dias. `reference_date`
        recorta até a data (dias posteriores fora) — permite reconstruir uma
        semana passada de forma honesta, igual ao RecoveryTrendAnalyzer."""

        if reference_date is not None:

            ref = reference_date.isoformat()

            series = [h for h in series if h.date <= ref]

        window = series[-_WINDOW_DAYS:]

        nights = [
            h.sleep_hours for h in window if h.sleep_hours is not None
        ]

        reading = SleepReading(nights_counted=len(nights))

        if not nights:

            return reading

        reading.avg_hours = round(sum(nights) / len(nights), 1)

        reading.last_night_hours = round(nights[-1], 1)

        reading.short_nights = sum(
            1 for s in nights if s < HEALTHY_FLOOR_HOURS
        )

        reading.debt = reading.avg_hours < HEALTHY_FLOOR_HOURS

        reading.direction = SleepReadingAnalyzer._direction(nights)

        reading.consistency = SleepReadingAnalyzer._consistency(nights)

        # a nota de sono da própria Garmin (recente), quando o relógio calcula
        reading.sleep_score = SleepReadingAnalyzer._last(
            [h.sleep_score for h in window]
        )

        deeps = [
            h.deep_sleep_hours
            for h in window
            if h.deep_sleep_hours is not None
        ]

        if deeps:

            reading.deep_avg_hours = round(sum(deeps) / len(deeps), 1)

        return reading

    # ------------------------------------------------------------------

    @staticmethod
    def _direction(nights: list[float]) -> str:
        """Metade recente vs anterior — dormir MAIS é melhorar (RISING)."""

        if len(nights) < _MIN_POINTS:

            return STABLE

        half = len(nights) // 2

        earlier = nights[:half]

        recent = nights[half:]

        change = (sum(recent) / len(recent)) - (sum(earlier) / len(earlier))

        if abs(change) < _HOURS_DELTA:

            return STABLE

        return RISING if change > 0 else FALLING

    @staticmethod
    def _consistency(nights: list[float]) -> str:
        """Regular vs irregular pela variabilidade — dormir 8h/4h/7h/5h é tão
        problema quanto dormir pouco. Neutro sem pontos suficientes."""

        if len(nights) < _MIN_POINTS:

            return "unknown"

        spread = statistics.pstdev(nights)

        return "irregular" if spread > _IRREGULAR_STDEV else "regular"

    @staticmethod
    def _last(values):
        """Último valor não-None (o estado mais atual)."""

        for v in reversed(values):

            if v is not None:

                return v

        return None
