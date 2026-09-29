"""Tendência dos sinais de recuperação (HRV, FC repouso, sono, stress, body
battery, VO2max) a partir da série diária de saúde do Garmin. Puro/testável.

Direção dos marcadores de ouro (HRV, FC de repouso) = a última semana contra a
FAIXA NORMAL do atleta (~2 meses); sem base suficiente, a metade recente contra
a anterior da janela. HRV subindo e FC de repouso caindo = recuperação/adaptação. Ver [[project_analise_corpo_garmin]]."""

from datetime import date

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
_BB_WAKE_DELTA = 5.0   # body battery ao acordar (pontos) — evita ruído de 1 noite
_RESP_DELTA = 1.0      # respiração no sono (rpm)

# noite curta (limitador de recuperação)
_SHORT_NIGHT_HOURS = 6.0

# FAIXA NORMAL DO ATLETA pros marcadores de ouro (HRV e FC de repouso): a última
# semana contra a faixa dele nos ~2 meses anteriores (média ± 1 desvio-padrão, no
# mínimo a folga fixa acima). Só é "piorando" quando SAI da faixa dele — não
# quando oscila dentro dela. Antes comparava a semana com a anterior com folga de
# 2 ms / 1,5 bpm: a oscilação normal virava alerta e os atletas passavam 75-80%
# do tempo "em alerta" (27/09). É como o próprio Garmin lê o HRV (status vs a
# linha de base pessoal).
_RECENT_DAYS = 7
_BASELINE_DAYS = 60
_MIN_BASELINE_POINTS = 14

# body battery ao acordar abaixo disto = acordou "no vermelho" (não recarregou)
# — aí sim é sinal de recuperação ruim. Acordar cheio (mesmo caindo de leve) não.
LOW_WAKE_BATTERY = 30


class RecoveryTrendAnalyzer:

    @staticmethod
    def analyze(
        series: list[DailyHealth],
        reference_date: date | None = None,
    ) -> RecoveryTrend:
        """Tendência dos últimos _WINDOW_DAYS dias. Com `reference_date`, olha
        só até aquela data (dias posteriores ficam de fora) — é o que permite
        reconstruir a leitura de uma semana PASSADA de forma honesta (backfill/
        trajetória), sem contaminar com o corpo de hoje. Sem ela, usa a série
        inteira (comportamento atual)."""

        if reference_date is not None:

            ref = reference_date.isoformat()

            series = [h for h in series if h.date <= ref]

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

        trend.hrv_direction = RecoveryTrendAnalyzer._band_direction(
            series,
            lambda h: (
                h.hrv_weekly_avg if h.hrv_weekly_avg is not None
                else h.hrv_last_night
            ),
            _HRV_DELTA,
            higher_is_better=True,
        ) or RecoveryTrendAnalyzer._direction(
            hrv, _HRV_DELTA, higher_is_better=True
        )

        rhr = [h.resting_hr for h in window]

        trend.rhr_recent = RecoveryTrendAnalyzer._last(rhr)

        trend.rhr_direction = RecoveryTrendAnalyzer._band_direction(
            series, lambda h: h.resting_hr, _RHR_DELTA, higher_is_better=False,
        ) or RecoveryTrendAnalyzer._direction(
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

        # números que a PRÓPRIA Garmin computa (relógios melhores) — o mais
        # recente da janela. Quando vêm, MANDAM: a leitura/painel mostra o
        # número do relógio em vez de derivar por conta ([[project_analise_corpo_garmin]]).
        trend.sleep_score = RecoveryTrendAnalyzer._last(
            [h.sleep_score for h in window]
        )

        trend.readiness_score = RecoveryTrendAnalyzer._last(
            [h.readiness_score for h in window]
        )

        trend.readiness_level = RecoveryTrendAnalyzer._last(
            [h.readiness_level for h in window]
        )

        trend.training_status = RecoveryTrendAnalyzer._last(
            [h.training_status for h in window]
        )

        trend.hrv_status = RecoveryTrendAnalyzer._last(
            [h.hrv_status for h in window]
        )

        RecoveryTrendAnalyzer._apply_tier2(trend, window)

        return trend

    @staticmethod
    def is_declining(trend: RecoveryTrend) -> bool:
        """A recuperação está PIORANDO? Marcadores de ouro (HRV e FC de repouso)
        pela DIREÇÃO contra a faixa dele; body battery só pelo NÍVEL absoluto
        (acordar no vermelho) — nunca pela direção com o tanque cheio (acordar em
        91 caindo de leve não é alerta). É a definição ÚNICA de "alerta": o
        veredito do corpo e a sequência de dias em alerta usam esta mesma régua."""

        waking_drained = (
            trend.body_battery_wake is not None
            and trend.body_battery_wake < LOW_WAKE_BATTERY
        )

        return (
            trend.hrv_direction == FALLING
            or trend.rhr_direction == FALLING
            or waking_drained
        )

    @staticmethod
    def _apply_tier2(trend: RecoveryTrend, window) -> None:
        """Sinais de contexto do tier-2: body battery ao acordar (marcador de
        recuperação, com direção), respiração no sono (sinal), SpO2 mínima
        (flag) e carga de vida (esforço fora do treino)."""

        wake = [h.body_battery_at_wake for h in window]

        trend.body_battery_wake = RecoveryTrendAnalyzer._last(wake)

        trend.body_battery_wake_direction = RecoveryTrendAnalyzer._direction(
            wake, _BB_WAKE_DELTA, higher_is_better=True
        )

        resp = [h.respiration_sleep_avg for h in window]

        trend.respiration_sleep = RecoveryTrendAnalyzer._last(resp)

        trend.respiration_direction = RecoveryTrendAnalyzer._direction(
            resp, _RESP_DELTA, higher_is_better=False  # respiração subir = pior
        )

        # SpO2 da noite: a MÉDIA de sono sustentada (não o vale de 1 noite)
        trend.spo2_sleep_avg = RecoveryTrendAnalyzer._last(
            [h.spo2_sleep_avg for h in window]
        )

        # carga de vida = média/dia dos dias que têm o dado
        trend.steps_avg = RecoveryTrendAnalyzer._avg(
            [h.steps for h in window]
        )

        trend.active_calories_avg = RecoveryTrendAnalyzer._avg(
            [h.active_calories for h in window]
        )

        # minutos intensos ponderados (vigorosa conta dobrado, como a Garmin):
        # média/dia de (moderada + 2×vigorosa)
        weighted = [
            (h.intensity_minutes_moderate or 0)
            + 2 * (h.intensity_minutes_vigorous or 0)
            for h in window
            if h.intensity_minutes_moderate is not None
            or h.intensity_minutes_vigorous is not None
        ]

        trend.intensity_minutes_avg = (
            round(sum(weighted) / len(weighted)) if weighted else None
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _last(values):
        """Último valor não-None da série (o estado mais atual)."""

        for v in reversed(values):

            if v is not None:

                return v

        return None

    @staticmethod
    def _avg(values):
        """Média (inteiro) dos valores não-None, ou None se não houver."""

        points = [v for v in values if v is not None]

        return round(sum(points) / len(points)) if points else None

    @staticmethod
    def _band_direction(
        series, value_of, delta: float, higher_is_better: bool,
    ) -> str | None:
        """A última semana contra a FAIXA NORMAL do atleta (média ± 1 DP dos ~2
        meses anteriores, mínimo `delta`). None quando não há base suficiente
        (aí vale a comparação semana × semana)."""

        import statistics

        recent = [
            v for v in (value_of(h) for h in series[-_RECENT_DAYS:])
            if v is not None
        ]

        baseline = [
            v for v in (
                value_of(h)
                for h in series[-(_BASELINE_DAYS + _RECENT_DAYS):-_RECENT_DAYS]
            )
            if v is not None
        ]

        if len(recent) < 3 or len(baseline) < _MIN_BASELINE_POINTS:

            return None

        margin = max(delta, statistics.pstdev(baseline))

        change = statistics.mean(recent) - statistics.mean(baseline)

        if abs(change) < margin:

            return STABLE

        improving = (change > 0) if higher_is_better else (change < 0)

        return RISING if improving else FALLING

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
