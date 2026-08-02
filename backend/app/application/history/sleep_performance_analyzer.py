"""Coaching de SONO: o custo REAL do sono curto no desempenho do atleta, com os
números DELE — não "durma mais" genérico. Correlaciona o sono da noite anterior
com a eficiência (velocidade por batimento) das corridas comparáveis: se as
corridas após noites curtas rendem menos NO MESMO ESFORÇO, mostramos quanto.

Puro/determinístico. Espelha a lógica do AerobicEfficiencyAnalyzer (EF =
velocidade ÷ FC), mas condicionado ao sono. Ver [[project_analise_corpo_garmin]]."""

import statistics
from datetime import date, timedelta

from app.core.clock import today_local
from app.domain.entities.activity import Activity
from app.domain.entities.daily_health import DailyHealth
from app.domain.entities.sleep_impact import SleepImpact
from app.domain.entities.sleep_reading import HEALTHY_FLOOR_HOURS
from app.domain.value_objects.sports import is_run_sport

# janela: economia e sono variam devagar; ~8 semanas (igual ao eixo de forma)
_WINDOW_DAYS = 56

# corrida curta demais é ruído
_MIN_KM = 3.0

# mínimo de corridas em CADA grupo (dormiu pouco / dormiu bem) pra comparar
_MIN_PER_GROUP = 3

# folga relativa do EF pra chamar de custo real (ruído de terreno/calor/dia)
_EF_NOISE = 0.03  # 3%

# custo mínimo (s/km) pra valer a pena reportar, e teto de credibilidade
_MIN_COST_SEC = 5
_MAX_COST_SEC = 40


class SleepPerformanceAnalyzer:

    @staticmethod
    def analyze(
        activities: list[Activity],
        health_series: list[DailyHealth],
        reference_date: date | None = None,
    ) -> SleepImpact:

        ref = reference_date or today_local()

        cutoff = ref - timedelta(days=_WINDOW_DAYS)

        sleep_by_day = {
            h.date: h.sleep_hours
            for h in health_series
            if h.sleep_hours is not None
        }

        low: list[float] = []      # EF das corridas após noite curta

        rested: list[float] = []   # EF das corridas após noite boa

        hrs: list[float] = []      # FC das comparáveis (referência da tradução)

        for a in activities:

            if not SleepPerformanceAnalyzer._comparable(a):

                continue

            run_day = a.start_date.date()

            if run_day < cutoff or run_day > ref:

                continue

            sleep = sleep_by_day.get(run_day.isoformat())

            if sleep is None:

                continue

            ef = a.average_speed / a.average_heartrate  # m/s por bpm

            hrs.append(a.average_heartrate)

            if sleep < HEALTHY_FLOOR_HOURS:

                low.append(ef)

            else:

                rested.append(ef)

        if len(low) < _MIN_PER_GROUP or len(rested) < _MIN_PER_GROUP:

            return SleepImpact(low_sleep_runs=len(low), rested_runs=len(rested))

        ef_low = statistics.median(low)

        ef_rested = statistics.median(rested)

        # sono curto RENDE MENOS = EF menor. Sem piora relevante: sem achado.
        if ef_rested <= 0 or (ef_rested - ef_low) / ef_rested < _EF_NOISE:

            return SleepImpact(
                low_sleep_runs=len(low), rested_runs=len(rested)
            )

        cost = SleepPerformanceAnalyzer._pace_cost_sec(
            ef_low, ef_rested, statistics.median(hrs)
        )

        if cost < _MIN_COST_SEC:

            return SleepImpact(
                low_sleep_runs=len(low), rested_runs=len(rested)
            )

        return SleepImpact(
            has_finding=True,
            pace_cost_sec=min(cost, _MAX_COST_SEC),
            low_sleep_runs=len(low),
            rested_runs=len(rested),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _comparable(a: Activity) -> bool:

        return (
            is_run_sport(a.sport)
            and a.average_speed > 0
            and (a.average_heartrate or 0) > 0
            and a.distance / 1000 >= _MIN_KM
        )

    @staticmethod
    def _pace_cost_sec(
        ef_low: float,
        ef_rested: float,
        hr_ref: float,
    ) -> int:
        """Traduz a queda de EF em s/km A MAIS no MESMO esforço: na FC de
        referência, quanto o pace piora dormindo pouco."""

        speed_low = ef_low * hr_ref       # m/s
        speed_rested = ef_rested * hr_ref

        pace_low = 1000 / speed_low / 60      # min/km
        pace_rested = 1000 / speed_rested / 60

        return round((pace_low - pace_rested) * 60)


def sleep_impact_plan_directive(impact: SleepImpact) -> str:
    """Diretriz COACH-facing pro plano: quando o sono curto custa desempenho ao
    atleta, o coach pesa isso na dose (protege semanas de dívida de sono). Vazio
    quando não há sinal — o prompt não ganha ruído."""

    if not impact.has_finding:

        return ""

    floor = int(impact.threshold_hours)

    return (
        f"Sono: dormindo abaixo de {floor}h, o pace dele no MESMO esforço cai "
        f"~{impact.pace_cost_sec}s/km (dado real dele). Pese na dose — em "
        "semana de dívida de sono, segure a mão em vez de forçar qualidade."
    )
