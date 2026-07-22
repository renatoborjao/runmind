"""Tendência dos sinais de recuperação (HRV, FC repouso, sono, stress, body
battery, VO2max) a partir da série diária de saúde do Garmin. Puro/testável.

Direção = compara a metade RECENTE com a ANTERIOR da janela (com folga pra
'estável'). HRV subindo e FC de repouso caindo são os dois marcadores de ouro
de recuperação/adaptação. Ver [[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import (
    FALLING,
    RISING,
    STABLE,
    RecoveryTrend,
)
from app.domain.entities.daily_health import DailyHealth

# janela de dias pra a tendência (o comportamento recente, não a vida toda)
_WINDOW_DAYS = 14

# mínimo de pontos pra arriscar uma direção (senão "stable")
_MIN_POINTS = 4

# folga pra chamar de "mudou" (ruído natural do dia a dia)
_HRV_DELTA = 2.0   # ms
_RHR_DELTA = 1.5   # bpm

# noite curta (limitador de recuperação)
_SHORT_NIGHT_HOURS = 6.0


class RecoveryTrendAnalyzer:

    @staticmethod
    def analyze(series: list[DailyHealth]) -> RecoveryTrend:

        window = series[-_WINDOW_DAYS:]

        trend = RecoveryTrend(days_covered=len(window))

        if not window:

            return trend

        # HRV: prefere a média semanal (mais estável); cai pro da noite
        hrv = [
            h.hrv_weekly_avg if h.hrv_weekly_avg is not None else h.hrv_last_night
            for h in window
        ]

        trend.hrv_recent = RecoveryTrendAnalyzer._last(hrv)

        trend.hrv_direction = RecoveryTrendAnalyzer._direction(
            hrv, _HRV_DELTA, higher_is_better=True
        )

        rhr = [h.resting_hr for h in window]

        trend.rhr_recent = RecoveryTrendAnalyzer._last(rhr)

        trend.rhr_direction = RecoveryTrendAnalyzer._direction(
            rhr, _RHR_DELTA, higher_is_better=False
        )

        sleeps = [h.sleep_hours for h in window if h.sleep_hours is not None]

        if sleeps:

            trend.sleep_avg_hours = round(sum(sleeps) / len(sleeps), 1)

            trend.short_nights = sum(1 for s in sleeps if s < _SHORT_NIGHT_HOURS)

            trend.nights_counted = len(sleeps)

        stresses = [h.stress_avg for h in window if h.stress_avg is not None]

        if stresses:

            trend.stress_avg = round(sum(stresses) / len(stresses))

        trend.body_battery_recent = RecoveryTrendAnalyzer._last(
            [h.body_battery_change for h in window]
        )

        trend.vo2max = RecoveryTrendAnalyzer._last(
            [h.vo2max for h in window]
        )

        return trend

    # ------------------------------------------------------------------

    @staticmethod
    def _last(values):
        """Último valor não-None da série (o estado mais atual)."""

        for v in reversed(values):

            if v is not None:

                return v

        return None

    @staticmethod
    def _direction(values, delta: float, higher_is_better: bool) -> str:
        """Compara a média da metade recente com a da anterior. Devolve, do
        ponto de vista da RECUPERAÇÃO: RISING (melhorando), FALLING (piorando)
        ou STABLE. Para HRV, subir = melhorar; pra FC repouso, cair = melhorar
        — o higher_is_better normaliza isso pra a semântica de recuperação."""

        points = [v for v in values if v is not None]

        if len(points) < _MIN_POINTS:

            return STABLE

        half = len(points) // 2

        earlier = points[:half]

        recent = points[half:]

        change = (sum(recent) / len(recent)) - (sum(earlier) / len(earlier))

        if abs(change) < delta:

            return STABLE

        going_up = change > 0

        # métrica melhorou? (subiu e subir é bom, ou caiu e cair é bom)
        improving = going_up if higher_is_better else not going_up

        return RISING if improving else FALLING
