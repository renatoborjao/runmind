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

from app.core.clock import today_local
from app.domain.entities.activity import Activity
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    EFF_INSUFFICIENT,
    EFF_STABLE,
    AerobicEfficiency,
)
from app.domain.value_objects.sports import is_run_sport

# janela de análise: eficiência muda devagar, então olhamos ~8 semanas
_WINDOW_DAYS = 56

# corrida curta demais é ruído (aquecimento, tiro isolado, teste)
_MIN_KM = 3.0

# mínimo de corridas aeróbicas pra arriscar uma direção (metade vs metade)
_MIN_RUNS = 6

# faixa aeróbica em %FCR: abaixo é caminhada/trote de recuperação, acima é
# tempo/tiro/prova (economia não comparável). Só aplicada com FC repouso+máx.
_AEROBIC_MIN_HRR = 0.45
_AEROBIC_MAX_HRR = 0.80

# folga relativa do EF pra chamar de "mudou" (ruído de terreno/calor/dia)
_EF_NOISE = 0.02  # 2%


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

        # metade recente vs anterior, na ordem cronológica
        half = len(runs) // 2

        earlier = runs[:half]

        recent = runs[half:]

        ef_earlier = statistics.median(r["ef"] for r in earlier)

        ef_recent = statistics.median(r["ef"] for r in recent)

        ref_hr = round(statistics.median(r["hr"] for r in runs))

        ref_pace = round(statistics.median(r["pace"] for r in runs), 2)

        direction = AerobicEfficiencyAnalyzer._direction(ef_earlier, ef_recent)

        pace_gain, hr_drop = AerobicEfficiencyAnalyzer._translate(
            ef_earlier, ef_recent, ref_hr, ref_pace
        )

        return AerobicEfficiency(
            direction=direction,
            runs_counted=len(runs),
            weeks_covered=AerobicEfficiencyAnalyzer._weeks_covered(runs),
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

            runs.append(
                {
                    "day": day,
                    "ef": speed / hr,           # m/s por batimento
                    "hr": hr,
                    "pace": (1000 / speed) / 60,  # min/km
                }
            )

        runs.sort(key=lambda r: r["day"])

        return runs

    @staticmethod
    def _direction(ef_earlier: float, ef_recent: float) -> str:
        """EF subiu além do ruído = mais econômico = melhorando."""

        if ef_earlier <= 0:

            return EFF_INSUFFICIENT

        change = (ef_recent - ef_earlier) / ef_earlier

        if abs(change) < _EF_NOISE:

            return EFF_STABLE

        return EFF_IMPROVING if change > 0 else EFF_DECLINING

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

    @staticmethod
    def _weeks_covered(runs: list[dict]) -> int:
        """Semanas entre a corrida mais antiga e a mais nova da janela."""

        span_days = (runs[-1]["day"] - runs[0]["day"]).days

        return max(1, round(span_days / 7))
