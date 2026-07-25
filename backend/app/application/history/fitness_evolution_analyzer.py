"""Veredito multi-sinal do "estou evoluindo?", triangulando o que já coletamos.

Cada sinal entra SÓ quando tem lastro (pontos/span mínimos) — assim a leitura
degrada com elegância: hoje, com saúde recém-conectada, o EF carrega sozinho e
o resto abstém; conforme VO₂máx/FC-repouso acumulam, ligam sozinhos (igual o
Edwards). Combina o que houver: sinais concordam → CLEAR; divergem → MIXED com
nuance. Puro/determinístico. Ver [[TrendEstimator]] e [[FitnessEvolution]]."""

from datetime import date, timedelta

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.application.history.trend_estimator import TrendEstimator
from app.core.clock import today_local
from app.domain.entities.activity import Activity
from app.domain.entities.daily_health import DailyHealth
from app.domain.entities.fitness_evolution import (
    EVO_CLEAR,
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    EVO_MARGINAL,
    EVO_MIXED,
    EVO_STABLE,
    FitnessEvolution,
)
from app.domain.entities.signal_trend import (
    TREND_DECLINING,
    TREND_IMPROVING,
    SignalTrend,
)

# horizonte longo: arco de meses ("evoluí desde que começamos a acompanhar?").
# Precisa cobrir bem mais que a janela curta pra dizer algo novo.
_LONG_WINDOW_DAYS = 168        # ~24 semanas
_LONG_MIN_SPAN_DAYS = 70       # ~10 semanas de alcance mínimo

# VO₂máx: número de fitness da própria Garmin. Muda devagar → ruído baixo.
_VO2_NOISE = 0.015
_VO2_MIN_POINTS = 6
_VO2_MIN_SPAN = 28

# FC de repouso: cair = adaptação aeróbica (sinal de APOIO). Ruidoso no dia a
# dia → exige mais pontos; invertido (cair é melhorar).
_RHR_NOISE = 0.02
_RHR_MIN_POINTS = 10
_RHR_MIN_SPAN = 28

# economia em ritmo FORTE (faixa limiar/tiro): a evolução que a rodagem não
# mostra. Mesma máquina de EF, faixa de esforço mais alta. Treino de qualidade
# é mais raro → exige menos pontos; janela longa pra juntar o suficiente.
_QUALITY_MIN_HRR = 0.82
_QUALITY_MAX_HRR = 0.95
_QUALITY_NOISE = 0.02
_QUALITY_MIN_POINTS = 5

# pesos na combinação: VO₂máx (número de fitness da Garmin) manda; EF (aeróbico)
# e economia em ritmo forte logo atrás; FC-repouso é apoio. Um sinal de apoio
# sozinho não decreta evolução.
_W_EF = 1.0
_W_QUALITY = 0.9
_W_VO2 = 1.3
_W_RHR = 0.7
_STABLE_BAND = 0.8


class FitnessEvolutionAnalyzer:

    @staticmethod
    def analyze(
        activities: list[Activity],
        health_series: list[DailyHealth],
        reference_date: date | None = None,
        resting_hr: int | None = None,
        max_hr: int | None = None,
    ) -> FitnessEvolution:

        ref = reference_date or today_local()

        # EF curto (janela ~8 sem) — o sinal sempre-presente, com tradução
        ef = AerobicEfficiencyAnalyzer.analyze(
            activities, reference_date=ref, resting_hr=resting_hr, max_hr=max_hr
        )

        ef_long = FitnessEvolutionAnalyzer._ef_long_trend(
            activities, ref, resting_hr, max_hr
        )

        quality = FitnessEvolutionAnalyzer._quality_ef_trend(
            activities, ref, resting_hr, max_hr
        )

        vo2max = FitnessEvolutionAnalyzer._health_trend(
            health_series, ref, "vo2max",
            noise=_VO2_NOISE, min_points=_VO2_MIN_POINTS,
            min_span=_VO2_MIN_SPAN, invert=False,
        )

        rhr = FitnessEvolutionAnalyzer._health_trend(
            health_series, ref, "resting_hr",
            noise=_RHR_NOISE, min_points=_RHR_MIN_POINTS,
            min_span=_RHR_MIN_SPAN, invert=True,
        )

        direction, confidence = FitnessEvolutionAnalyzer._combine(
            ef, ef_long, quality, vo2max, rhr
        )

        return FitnessEvolution(
            direction=direction,
            confidence=confidence,
            ef=ef if ef.has_data else None,
            ef_long=ef_long,
            quality=quality,
            vo2max=vo2max,
            rhr=rhr,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _ef_long_trend(
        activities: list[Activity],
        ref: date,
        resting_hr: int | None,
        max_hr: int | None,
    ) -> SignalTrend | None:
        """A MESMA economia aeróbica, mas no arco longo (meses). Reaproveita o
        filtro de corridas comparáveis do analisador curto."""

        start = ref - timedelta(days=_LONG_WINDOW_DAYS - 1)

        runs = AerobicEfficiencyAnalyzer._comparable_runs(
            activities, start, ref, resting_hr, max_hr
        )

        return TrendEstimator.estimate(
            [(r["day"], r["ef"]) for r in runs],
            noise_pct=0.02,
            min_points=8,
            min_span_days=_LONG_MIN_SPAN_DAYS,
        )

    @staticmethod
    def _quality_ef_trend(
        activities: list[Activity],
        ref: date,
        resting_hr: int | None,
        max_hr: int | None,
    ) -> SignalTrend | None:
        """Economia (EF) na faixa de ritmo FORTE (limiar/tiro) — a evolução que
        a rodagem não mostra. Só faz sentido com FC repouso+máx (pra isolar a
        faixa); sem elas, abstém. Janela longa (treino de qualidade é raro)."""

        if not (resting_hr and max_hr and max_hr > resting_hr):

            return None

        start = ref - timedelta(days=_LONG_WINDOW_DAYS - 1)

        runs = AerobicEfficiencyAnalyzer._comparable_runs(
            activities, start, ref, resting_hr, max_hr,
            hrr_min=_QUALITY_MIN_HRR, hrr_max=_QUALITY_MAX_HRR,
        )

        return TrendEstimator.estimate(
            [(r["day"], r["ef"]) for r in runs],
            noise_pct=_QUALITY_NOISE,
            min_points=_QUALITY_MIN_POINTS,
            min_span_days=_LONG_MIN_SPAN_DAYS,
        )

    @staticmethod
    def _health_trend(
        series: list[DailyHealth],
        ref: date,
        attr: str,
        *,
        noise: float,
        min_points: int,
        min_span: int,
        invert: bool,
    ) -> SignalTrend | None:
        """Tendência de uma métrica de saúde (VO₂máx, FC-repouso) na janela
        longa. Um ponto por dia que tem o valor; abstém sem lastro."""

        start = ref - timedelta(days=_LONG_WINDOW_DAYS - 1)

        points: list[tuple[date, float]] = []

        for h in series:

            value = getattr(h, attr, None)

            if value is None:

                continue

            day = date.fromisoformat(h.date)

            if not (start <= day <= ref):

                continue

            points.append((day, float(value)))

        return TrendEstimator.estimate(
            points,
            noise_pct=noise,
            min_points=min_points,
            min_span_days=min_span,
            invert=invert,
        )

    @staticmethod
    def _combine(ef, ef_long, quality, vo2max, rhr) -> tuple[str, str]:
        """Funde os sinais num veredito + confiança. Ausente não vota;
        concordância → CLEAR; divergência → MIXED. O EF longo NÃO pontua na
        direção (é a mesma métrica do curto — evita dupla contagem), mas
        corrobora a confiança quando concorda de forma clara."""

        votes = []  # (direction_improving_bool_or_none, weight, clear)

        if ef is not None and ef.has_data:

            votes.append(
                (
                    FitnessEvolutionAnalyzer._ef_vote(ef.direction),
                    _W_EF,
                    False,   # o EF curto não carrega confiança explícita
                )
            )

        for trend, weight in (
            (quality, _W_QUALITY), (vo2max, _W_VO2), (rhr, _W_RHR)
        ):

            if trend is not None:

                votes.append(
                    (
                        FitnessEvolutionAnalyzer._trend_vote(trend.direction),
                        weight,
                        trend.clear,
                    )
                )

        if not votes:

            return EVO_INSUFFICIENT, EVO_MARGINAL

        score = sum(w for v, w, _ in votes if v is True)

        score -= sum(w for v, w, _ in votes if v is False)

        has_up = any(v is True for v, _, _ in votes)

        has_down = any(v is False for v, _, _ in votes)

        if score > _STABLE_BAND:

            direction = EVO_IMPROVING

        elif score < -_STABLE_BAND:

            direction = EVO_DECLINING

        else:

            direction = EVO_STABLE

        confidence = FitnessEvolutionAnalyzer._confidence(
            direction, votes, ef_long, has_up, has_down
        )

        return direction, confidence

    @staticmethod
    def _confidence(direction, votes, ef_long, has_up, has_down) -> str:
        """Sinais opostos = MIXED; senão CLEAR quando há corroboração (2+
        sinais concordando, um sinal forte com confiança, OU o EF longo
        confirmando de forma clara a mesma direção); senão MARGINAL."""

        if has_up and has_down:

            return EVO_MIXED

        agreeing = [v for v, _, _ in votes if v is not None]

        any_clear = any(c for _, _, c in votes)

        # EF longo corrobora: mesma direção do veredito E estatisticamente claro
        long_confirms = (
            ef_long is not None
            and ef_long.clear
            and direction != EVO_STABLE
            and FitnessEvolutionAnalyzer._trend_vote(ef_long.direction)
            == (direction == EVO_IMPROVING)
        )

        if len(agreeing) >= 2 or any_clear or long_confirms:

            return EVO_CLEAR

        return EVO_MARGINAL

    @staticmethod
    def _ef_vote(ef_direction: str) -> bool | None:
        """EFF_* -> voto (True melhora, False piora, None estável)."""

        from app.domain.entities.aerobic_efficiency import (
            EFF_DECLINING,
            EFF_IMPROVING,
        )

        if ef_direction == EFF_IMPROVING:

            return True

        if ef_direction == EFF_DECLINING:

            return False

        return None

    @staticmethod
    def _trend_vote(trend_direction: str) -> bool | None:

        if trend_direction == TREND_IMPROVING:

            return True

        if trend_direction == TREND_DECLINING:

            return False

        return None
