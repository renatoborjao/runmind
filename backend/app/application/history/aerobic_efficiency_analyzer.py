"""Eficiência aeróbica ao longo do tempo (o eixo "estou evoluindo?").

Fitness aeróbico = correr mais rápido para cada batimento. Medimos pelo
Efficiency Factor (EF = velocidade ÷ FC média) das corridas EASY/aeróbicas
comparáveis e comparamos a metade RECENTE com a ANTERIOR da janela — EF subindo
= corpo mais econômico = mais em forma. Puro/testável, sem IO.

Só corridas comparáveis entram: corrida de verdade (não caminhada), com FC, de
distância mínima, e — quando dá pra estimar %FCR — dentro da faixa aeróbica
(fora tiro/prova/all-out, cuja economia não se compara a rodagem leve). Ver
[[project_analise_corpo_garmin]] e [[project_ideias_produto]]."""

import statistics
from datetime import date, timedelta

from app.application.history.trend_estimator import TrendEstimator
from app.core.clock import today_local
from app.domain.entities.activity import Activity
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    EFF_INSUFFICIENT,
    EFF_STABLE,
    AerobicEfficiency,
)
from app.domain.entities.signal_trend import (
    TREND_DECLINING,
    TREND_IMPROVING,
)
from app.domain.value_objects.sports import is_run_sport

# janela de análise: eficiência muda devagar, então olhamos ~8 semanas
_WINDOW_DAYS = 56

# corrida curta demais é ruído (aquecimento, tiro isolado, teste)
_MIN_KM = 3.0

# mínimo de corridas aeróbicas pra arriscar uma direção
_MIN_RUNS = 6

# span mínimo (dias) entre a 1ª e a última corrida — sem alcance temporal a
# regressão não significa nada (6 corridas em 4 dias não é tendência)
_MIN_SPAN_DAYS = 14

# faixa aeróbica em %FCR: abaixo é caminhada/trote de recuperação, acima é
# tempo/tiro/prova (economia não comparável). Só aplicada com FC repouso+máx.
_AEROBIC_MIN_HRR = 0.45
_AEROBIC_MAX_HRR = 0.80

# folga relativa do EF pra chamar de "mudou" (ruído de terreno/calor/dia)
_EF_NOISE = 0.02  # 2%

# normalização de calor: acima da temperatura de conforto a FC sobe pro mesmo
# ritmo (deriva térmica). Corrige a FC de volta a uma referência amena pra o
# EF de um treino quente não parecer perda de forma. Coeficiente CONSERVADOR
# (a literatura vai de ~0,2 a >0,6 bpm/°C; ficamos no piso), teto pra não
# exagerar, e só desconta calor (frio não infla FC). Aplicada por corrida,
# só quando a temperatura veio do Strava. Ver [[project_ideias_produto]].
_HEAT_REF_C = 15.0
_HEAT_COEF_BPM_PER_C = 0.30
_HEAT_MAX_CORRECTION_BPM = 8.0


class AerobicEfficiencyAnalyzer:

    @staticmethod
    def analyze(
        activities: list[Activity],
        reference_date: date | None = None,
        resting_hr: int | None = None,
        max_hr: int | None = None,
    ) -> AerobicEfficiency:
        """Tendência do Efficiency Factor na janela. Com `resting_hr` E
        `max_hr`, filtra as corridas pela faixa aeróbica (%FCR) — o mais
        honesto; sem eles, usa todas as corridas com FC (EF já normaliza pace
        por FC, então segue direcional, só mais ruidoso). `reference_date`
        permite reconstruir uma janela passada sem contaminar com o hoje."""

        ref = reference_date or today_local()

        start = ref - timedelta(days=_WINDOW_DAYS - 1)

        runs = AerobicEfficiencyAnalyzer._comparable_runs(
            activities, start, ref, resting_hr, max_hr
        )

        if len(runs) < _MIN_RUNS:

            return AerobicEfficiency(
                direction=EFF_INSUFFICIENT, runs_counted=len(runs)
            )

        # tendência do EF por REGRESSÃO (reta sobre TODAS as corridas) — bem
        # menos sensível a um treino atípico que o antigo metade-vs-metade, e
        # ainda entrega confiança (R²). Os extremos AJUSTADOS da reta viram o
        # "antes" e o "depois" pra tradução tangível.
        trend = TrendEstimator.estimate(
            [(r["day"], r["ef"]) for r in runs],
            noise_pct=_EF_NOISE,
            min_points=_MIN_RUNS,
            min_span_days=_MIN_SPAN_DAYS,
        )

        if trend is None:

            return AerobicEfficiency(
                direction=EFF_INSUFFICIENT, runs_counted=len(runs)
            )

        ef_earlier = trend.earlier_value

        ef_recent = trend.recent_value

        ref_hr = round(statistics.median(r["hr"] for r in runs))

        ref_pace = round(statistics.median(r["pace"] for r in runs), 2)

        direction = AerobicEfficiencyAnalyzer._map_direction(trend.direction)

        pace_gain, hr_drop = AerobicEfficiencyAnalyzer._translate(
            ef_earlier, ef_recent, ref_hr, ref_pace
        )

        return AerobicEfficiency(
            direction=direction,
            runs_counted=len(runs),
            weeks_covered=trend.span_weeks,
            ef_recent=round(ef_recent, 5),
            ef_earlier=round(ef_earlier, 5),
            ref_hr=ref_hr,
            ref_pace=ref_pace,
            pace_gain_sec=pace_gain,
            hr_drop_bpm=hr_drop,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _comparable_runs(
        activities: list[Activity],
        start: date,
        ref: date,
        resting_hr: int | None,
        max_hr: int | None,
    ) -> list[dict]:
        """Corridas aeróbicas comparáveis na janela, em ordem cronológica,
        cada uma com seu EF (velocidade ÷ FC), FC média e pace."""

        band = (
            resting_hr is not None
            and max_hr is not None
            and max_hr > resting_hr
        )

        runs = []

        for a in activities:

            day = a.start_date.date()

            if not (start <= day <= ref):

                continue

            if not is_run_sport(a.sport):

                continue

            if (a.distance or 0) < _MIN_KM * 1000:

                continue

            hr = a.average_heartrate

            speed = a.average_speed

            if not hr or hr <= 0 or not speed or speed <= 0:

                continue

            if band:

                hrr = (hr - resting_hr) / (max_hr - resting_hr)

                if not (_AEROBIC_MIN_HRR <= hrr <= _AEROBIC_MAX_HRR):

                    continue

            # EF = velocidade por batimento, com a FC normalizada pelo calor
            # (treino quente não deve parecer perda de economia)
            eff_hr = AerobicEfficiencyAnalyzer._heat_normalized_hr(
                hr, getattr(a, "air_temp_c", None)
            )

            runs.append(
                {
                    "day": day,
                    "ef": speed / eff_hr,       # m/s por batimento (normalizado)
                    "hr": hr,                    # FC real (pra exibição/ref)
                    "pace": (1000 / speed) / 60,  # min/km
                }
            )

        runs.sort(key=lambda r: r["day"])

        return runs

    @staticmethod
    def _heat_normalized_hr(hr: float, temp: float | None) -> float:
        """Desconta da FC a deriva térmica acima da temperatura de conforto,
        pra comparar treino quente com treino ameno na mesma régua. Só desconta
        calor (frio não infla FC), com teto. Sem temperatura → FC crua."""

        if temp is None or temp <= _HEAT_REF_C:

            return hr

        correction = min(
            _HEAT_COEF_BPM_PER_C * (temp - _HEAT_REF_C),
            _HEAT_MAX_CORRECTION_BPM,
        )

        return hr - correction

    @staticmethod
    def _map_direction(trend_direction: str) -> str:
        """Direção do primitivo de tendência -> vocabulário do EF."""

        if trend_direction == TREND_IMPROVING:

            return EFF_IMPROVING

        if trend_direction == TREND_DECLINING:

            return EFF_DECLINING

        return EFF_STABLE

    @staticmethod
    def _translate(
        ef_earlier: float,
        ef_recent: float,
        ref_hr: int,
        ref_pace: float,
    ) -> tuple[int | None, int | None]:
        """Traduz a variação de EF em algo sentível, sinal positivo = melhora:
        - na MESMA FC de referência, quantos s/km mais rápido (velocidade = EF×FC);
        - no MESMO pace de referência, quantos bpm a menos (FC = velocidade÷EF)."""

        if ef_earlier <= 0 or ef_recent <= 0:

            return None, None

        # na mesma FC: pace = 1000 / (EF × FC × 60)
        pace_earlier = 1000 / (ef_earlier * ref_hr * 60)

        pace_recent = 1000 / (ef_recent * ref_hr * 60)

        pace_gain = round((pace_earlier - pace_recent) * 60)  # s/km, + = mais rápido

        # no mesmo pace: FC = velocidade / EF, velocidade = 1000 / (pace × 60)
        speed_ref = 1000 / (ref_pace * 60)

        hr_earlier = speed_ref / ef_earlier

        hr_recent = speed_ref / ef_recent

        hr_drop = round(hr_earlier - hr_recent)  # bpm, + = FC menor (melhor)

        return pace_gain, hr_drop
