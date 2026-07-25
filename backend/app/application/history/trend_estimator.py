"""Estima a tendência de uma série temporal por REGRESSÃO LINEAR (OLS) — o
primitivo robusto que substitui o grosseiro "metade recente vs anterior".

Uma reta ajustada a TODOS os pontos (não só a duas médias) é bem menos sensível
a um treino atípico e ainda entrega um grau de confiança (R² = quão linear é a
tendência). O mesmo estimador serve os três sinais de forma (EF, VO₂máx,
FC-repouso) e os dois horizontes (curto/longo) — genérico, puro, sem IO.

`invert=True` orienta sinais em que CAIR é MELHORAR (FC-repouso): a variação
relativa devolvida fica sempre positiva = melhora. Ver [[SignalTrend]]."""

from datetime import date

from app.domain.entities.signal_trend import (
    CONF_CLEAR,
    CONF_MARGINAL,
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_STABLE,
    SignalTrend,
)


class TrendEstimator:

    @staticmethod
    def estimate(
        points: list[tuple[date, float]],
        *,
        noise_pct: float,
        min_points: int,
        min_span_days: int,
        invert: bool = False,
    ) -> SignalTrend | None:
        """Reta OLS sobre (dia, valor). None quando não há lastro (poucos
        pontos ou span curto) — o chamador degrada com elegância. `noise_pct`
        é a folga relativa pra chamar de "mudou" (abaixo dela = estável)."""

        pts = sorted(points, key=lambda p: p[0])

        if len(pts) < min_points:

            return None

        d0 = pts[0][0]

        xs = [(d - d0).days for d, _ in pts]

        ys = [float(v) for _, v in pts]

        span = xs[-1]

        if span < min_span_days:

            return None

        n = len(pts)

        sx = sum(xs)
        sy = sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))

        denom = n * sxx - sx * sx

        mean_y = sy / n

        if denom == 0 or mean_y == 0:

            return None

        slope = (n * sxy - sx * sy) / denom

        intercept = (sy - slope * sx) / n

        # R²: quão linear é a tendência (0 = ruído puro, 1 = reta perfeita)
        ss_tot = sum((y - mean_y) ** 2 for y in ys)

        ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))

        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # variação PROJETADA pela reta ao longo do span, em fração da média
        rel_change = (slope * span) / mean_y

        oriented = -rel_change if invert else rel_change

        if abs(oriented) < noise_pct:

            direction = TREND_STABLE

        elif oriented > 0:

            direction = TREND_IMPROVING

        else:

            direction = TREND_DECLINING

        confidence = (
            CONF_CLEAR
            if abs(oriented) >= 2 * noise_pct and r_squared >= 0.3
            else CONF_MARGINAL
        )

        return SignalTrend(
            direction=direction,
            confidence=confidence,
            points=n,
            span_days=span,
            span_weeks=max(1, round(span / 7)),
            relative_change=round(oriented, 4),
            # 6 casas: o EF vale ~0,016 — arredondar curto destrói a precisão
            # da tradução (pace_gain/hr_drop); inócuo pra VO₂máx/FC-repouso
            per_week=round(slope * 7, 6),
            r_squared=round(r_squared, 3),
            recent_value=round(intercept + slope * span, 6),
            earlier_value=round(intercept, 6),
            mean_value=round(mean_y, 6),
        )
