"""Detector de ESTRESSE FISIOLÓGICO AGUDO — o padrão "FC de repouso SALTA + HRV
CAI" nas últimas noites contra a LINHA DE BASE do próprio atleta. É o marcador
que a ciência (ex.: estudos de RHR/HRV vestível na era COVID) associa a
overreaching e ao INÍCIO de uma infecção (pré-gripe).

NÃO diagnostica doença — sinaliza o PADRÃO pra o coach orientar pegar leve
(o atleta decide; se vier sintoma, procurar profissional). Puro/determinístico,
custo zero de IA. Complementa a leitura de corpo (que é carga×tendência) com um
sinal AGUDO e independente de carga. Ver [[project_analise_corpo_garmin]]."""

from dataclasses import dataclass
from statistics import median

from app.domain.entities.daily_health import DailyHealth

# a "foto" recente (últimas 1-2 noites) vs a linha de base (o normal do atleta)
_RECENT_DAYS = 2
_BASELINE_DAYS = 21

# base mínima de noites com dado pra confiar num "normal"
_MIN_BASELINE = 7

# gatilhos — AMBOS têm que bater (sinal específico, baixo falso-positivo):
_RHR_SPIKE = 5.0       # FC de repouso >= 5 bpm acima da base
_HRV_DROP_PCT = 0.08   # HRV >= 8% abaixo da base


@dataclass(frozen=True)
class StrainVerdict:

    is_strained: bool

    rhr_recent: float | None = None

    rhr_baseline: float | None = None

    hrv_recent: float | None = None

    hrv_baseline: float | None = None


class AcuteStrainAnalyzer:

    @staticmethod
    def detect(series: list[DailyHealth]) -> StrainVerdict:
        """Compara as últimas noites com a base do atleta. `is_strained` só
        quando FC-repouso subiu E HRV caiu além do ruído — o padrão agudo."""

        if len(series) < _RECENT_DAYS + _MIN_BASELINE:

            return StrainVerdict(is_strained=False)

        recent = series[-_RECENT_DAYS:]

        baseline = series[-(_RECENT_DAYS + _BASELINE_DAYS):-_RECENT_DAYS]

        rhr_recent = AcuteStrainAnalyzer._med(h.resting_hr for h in recent)

        hrv_recent = AcuteStrainAnalyzer._med(h.hrv_last_night for h in recent)

        rhr_values = [h.resting_hr for h in baseline if h.resting_hr is not None]

        hrv_values = [
            h.hrv_last_night for h in baseline if h.hrv_last_night is not None
        ]

        # base insuficiente num dos eixos → não arrisca
        if (
            len(rhr_values) < _MIN_BASELINE
            or len(hrv_values) < _MIN_BASELINE
            or rhr_recent is None
            or hrv_recent is None
        ):

            return StrainVerdict(is_strained=False)

        rhr_baseline = median(rhr_values)

        hrv_baseline = median(hrv_values)

        rhr_up = rhr_recent - rhr_baseline >= _RHR_SPIKE

        hrv_down = hrv_recent <= hrv_baseline * (1 - _HRV_DROP_PCT)

        return StrainVerdict(
            is_strained=rhr_up and hrv_down,
            rhr_recent=round(rhr_recent, 1),
            rhr_baseline=round(rhr_baseline, 1),
            hrv_recent=round(hrv_recent, 1),
            hrv_baseline=round(hrv_baseline, 1),
        )

    @staticmethod
    def _med(values) -> float | None:
        """Mediana dos valores não-None (robusta a uma noite fora da curva)."""

        points = [v for v in values if v is not None]

        return median(points) if points else None
