"""O sono curto PREJUDICA a execução DESTE atleta, ou não? — a sabedoria que
separa "dorme pouco e entrega" de "dorme pouco e cai". Puro/determinístico,
ancorado no DADO real: pega as corridas comparáveis (mesma faixa aeróbica) e
compara a ECONOMIA (velocidade÷FC) das que vieram depois de noites CURTAS vs
noites NORMAIS (split pela mediana de sono DELE — "curto" é relativo a cada um).

Cada caso é um caso: uns rendem igual com pouco sono, outros despencam. O coach
lê o veredito e dosa com base nele — não numa regra genérica de "sono curto =
alivia". Dormir mais é sempre melhor, mas nem sempre dá; o que importa é se
está pesando NA ENTREGA. Ver [[project_analise_corpo_garmin]] e
[[feedback_base_historico_sempre]]."""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.core.clock import today_local
from app.domain.entities.activity import Activity

# mesma janela da eficiência (economia muda devagar)
_WINDOW_DAYS = 56

# mínimo de corridas em CADA grupo (curto/normal) pra arriscar um veredito
_MIN_PER_GROUP = 3

# a mediana de sono dos dois grupos precisa diferir o bastante pra o split
# significar algo — se ele dorme sempre ~6h, "curto vs normal" é 5.9 vs 6.1 e
# não há contraste real pra julgar
_MIN_SLEEP_CONTRAST_H = 0.5

# queda relativa de economia que já conta como "o sono pesou" (acima do ruído)
_HURT_THRESHOLD = 0.03  # 3%

SLEEP_HURTS = "HURTS"
SLEEP_SUSTAINS = "SUSTAINS"
SLEEP_INSUFFICIENT = "INSUFFICIENT"


@dataclass(slots=True)
class SleepPerformanceReading:

    direction: str

    runs_short: int = 0

    runs_rested: int = 0

    short_sleep_h: float | None = None

    rested_sleep_h: float | None = None

    # quanto mais LENTO (s/km, na mesma FC) ele fica após noites curtas; negativo
    # = até mais rápido. Só quando há veredito.
    pace_delta_sec: int | None = None


class SleepPerformanceAnalyzer:

    @staticmethod
    def assess(
        activities: list[Activity],
        health: list,
        resting_hr: int | None = None,
        max_hr: int | None = None,
        reference_date: date | None = None,
    ) -> SleepPerformanceReading:

        ref = reference_date or today_local()

        start = ref - timedelta(days=_WINDOW_DAYS - 1)

        runs = AerobicEfficiencyAnalyzer._comparable_runs(
            activities, start, ref, resting_hr, max_hr
        )

        sleep_by_date = {
            h.date: h.sleep_hours
            for h in health
            if getattr(h, "sleep_hours", None) is not None
        }

        # cada corrida com o sono da NOITE ANTERIOR (o sono do dia do treino, no
        # padrão Garmin, é a noite que antecede a corrida daquele dia)
        paired = [
            (r["ef"], r["hr"], sleep_by_date[r["day"].isoformat()])
            for r in runs
            if r["day"].isoformat() in sleep_by_date
        ]

        if len(paired) < 2 * _MIN_PER_GROUP:

            return SleepPerformanceReading(direction=SLEEP_INSUFFICIENT)

        median_sleep = statistics.median(s for _, _, s in paired)

        short = [(ef, hr, s) for ef, hr, s in paired if s < median_sleep]
        rested = [(ef, hr, s) for ef, hr, s in paired if s >= median_sleep]

        if len(short) < _MIN_PER_GROUP or len(rested) < _MIN_PER_GROUP:

            return SleepPerformanceReading(direction=SLEEP_INSUFFICIENT)

        short_sleep = statistics.median(s for _, _, s in short)
        rested_sleep = statistics.median(s for _, _, s in rested)

        # sem contraste de sono real entre os grupos: não dá pra julgar
        if rested_sleep - short_sleep < _MIN_SLEEP_CONTRAST_H:

            return SleepPerformanceReading(direction=SLEEP_INSUFFICIENT)

        ef_short = statistics.median(ef for ef, _, _ in short)
        ef_rested = statistics.median(ef for ef, _, _ in rested)

        drop = (ef_rested - ef_short) / ef_rested if ef_rested else 0.0

        ref_hr = round(statistics.median(hr for _, hr, _ in paired))

        pace_delta = SleepPerformanceAnalyzer._pace_delta(
            ef_short, ef_rested, ref_hr
        )

        direction = SLEEP_HURTS if drop >= _HURT_THRESHOLD else SLEEP_SUSTAINS

        return SleepPerformanceReading(
            direction=direction,
            runs_short=len(short),
            runs_rested=len(rested),
            short_sleep_h=round(short_sleep, 1),
            rested_sleep_h=round(rested_sleep, 1),
            pace_delta_sec=pace_delta,
        )

    @staticmethod
    def _pace_delta(ef_short: float, ef_rested: float, ref_hr: int) -> int | None:
        """Na mesma FC de referência, quantos s/km mais LENTO ele fica após
        noites curtas (positivo = mais lento). pace = 1000/(EF×FC×60)."""

        if ef_short <= 0 or ef_rested <= 0 or ref_hr <= 0:

            return None

        pace_short = 1000 / (ef_short * ref_hr * 60)
        pace_rested = 1000 / (ef_rested * ref_hr * 60)

        return round((pace_short - pace_rested) * 60)


def sleep_performance_directive(reading: SleepPerformanceReading) -> str:
    """Diretriz pro coach (plano): o veredito de sono×execução vira orientação
    de dose. Vazio sem lastro (INSUFFICIENT) — o coach segue pela leitura de
    corpo normal."""

    if reading.direction == SLEEP_INSUFFICIENT:

        return ""

    short = reading.short_sleep_h
    rested = reading.rested_sleep_h

    if reading.direction == SLEEP_SUSTAINS:

        return (
            "EVIDÊNCIA (sono × execução, do histórico REAL dele): depois de "
            f"noites CURTAS (~{short}h) ele entrega IGUAL às noites normais "
            f"(~{rested}h) — a economia dos treinos se mantém. Pra ELE, o sono "
            "curto é rotina e NÃO está prejudicando a execução: NÃO trave a dose "
            "por causa do sono. (Dormir mais é sempre melhor, mas ele rende "
            "assim.)"
        )

    delta = reading.pace_delta_sec or 0

    return (
        "EVIDÊNCIA (sono × execução, do histórico REAL dele): depois de noites "
        f"CURTAS (~{short}h) a execução dele CAI (~{delta}s/km mais lento na "
        f"mesma FC) vs noites normais (~{rested}h). Pra ELE, o sono curto PESA "
        "na entrega: quando vier uma fase de noites curtas, segure a "
        "intensidade e priorize recuperar — não empilhe qualidade em cima do "
        "cansaço."
    )
