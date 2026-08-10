"""Detecta quando o atleta ficou EM SILÊNCIO — nem treino nem conversa há tempo
demais PRA O PADRÃO DELE. É o gatilho do re-engajamento: o coach vai atrás em
vez de esperar (a peça de retenção que faltava; ver [[project_ideias_produto]]).

Pattern-aware (LEI [[feedback_base_historico_sempre]]): quem corre 3x/semana
sumido há 6 dias é notícia; quem corre 1x/semana, não. O limiar sai do ritmo
REAL de treino do atleta, não de um número fixo. Puro/determinístico."""

from dataclasses import dataclass
from datetime import date
from statistics import median

# o silêncio vira notícia quando passa de ~2.5x o intervalo típico entre
# treinos do atleta — folga suficiente pra não cutucar num descanso normal.
_GAP_MULTIPLIER = 2.5

# piso/teto do limiar (dias): nunca cutuca antes de ~1 semana, nem espera mais
# de 2 (passou disso, já sumiu — um toque só, sem repetir).
_MIN_THRESHOLD = 6
_MAX_THRESHOLD = 14

# intervalo típico assumido quando ainda não dá pra medir o padrão (1-2 treinos)
_DEFAULT_GAP = 3.0

# precisa ter COMEÇADO (≥1 corrida) pra haver o que re-engajar — atleta
# novíssimo/sem treino não é "silêncio", é onboarding.
_MIN_RUNS = 1


@dataclass(frozen=True)
class SilenceVerdict:

    is_dark: bool

    days_silent: int

    last_active: date | None

    typical_gap_days: float

    threshold_days: int

    @property
    def episode_key(self) -> str:
        """Chave do EPISÓDIO de silêncio (pro dedup): muda quando o atleta dá
        sinal de vida (treina/conversa) → um toque por episódio, nunca repete
        ([[feedback_orientar_nao_mandar]])."""

        return self.last_active.isoformat() if self.last_active else "none"


class SilenceDetector:

    @staticmethod
    def assess(
        run_dates: list[date],
        last_inbound: date | None,
        today: date,
    ) -> SilenceVerdict:
        """`run_dates` = datas das corridas reais; `last_inbound` = última vez
        que o atleta MANDOU mensagem (None se nunca); `today` = hoje local."""

        runs = sorted(d for d in run_dates if d is not None)

        gap = SilenceDetector._typical_gap(runs)

        threshold = SilenceDetector._threshold(gap)

        # sinal de vida mais recente: treino OU conversa
        candidates = [d for d in (runs[-1] if runs else None, last_inbound) if d]

        last_active = max(candidates) if candidates else None

        days_silent = (today - last_active).days if last_active else 0

        started = len(runs) >= _MIN_RUNS

        is_dark = started and last_active is not None and days_silent >= threshold

        return SilenceVerdict(
            is_dark=is_dark,
            days_silent=days_silent,
            last_active=last_active,
            typical_gap_days=round(gap, 1),
            threshold_days=threshold,
        )

    @staticmethod
    def _typical_gap(runs: list[date]) -> float:
        """Mediana dos intervalos entre corridas consecutivas (o ritmo real).
        Sem ao menos 2 intervalos, assume o default conservador."""

        if len(runs) < 3:

            return _DEFAULT_GAP

        gaps = [
            (runs[i] - runs[i - 1]).days
            for i in range(1, len(runs))
            if (runs[i] - runs[i - 1]).days > 0
        ]

        return median(gaps) if gaps else _DEFAULT_GAP

    @staticmethod
    def _threshold(gap: float) -> int:

        raw = round(gap * _GAP_MULTIPLIER)

        return max(_MIN_THRESHOLD, min(_MAX_THRESHOLD, raw))
