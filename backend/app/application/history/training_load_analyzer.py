"""Radar de sobrecarga (camada 2): calcula a CARGA de treino aguda (7d) vs
crônica (28d) e o ACWR a partir do histórico de atividades — pra QUALQUER
atleta, sem depender do 'training load' que só os relógios Garmin top dão.

Carga = minutos de treino (duração). Puro/testável, sem IO. Não decide nada
sozinho nem fala com o atleta — entrega o retrato pra a camada 3 (síntese)
consumir. Ver [[project_analise_corpo_garmin]]."""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from app.core.clock import today_local
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_load import (
    ACWR_CAUTION_MAX,
    ACWR_DETRAINING,
    ACWR_OPTIMAL_MAX,
    LOAD_CAUTION,
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
    TrainingLoad,
)

# a crônica precisa de ~3 semanas pra ser um baseline honesto; com menos, o
# ACWR fica instável (divisor pequeno infla a razão), então não arriscamos um
# veredito — devolve INSUFFICIENT_DATA.
_MIN_HISTORY_DAYS = 21

_ACUTE_DAYS = 7
_CHRONIC_DAYS = 28

# fator de intensidade da sessão SEM FC (raro): usa a mediana do próprio
# atleta; sem nenhuma sessão com FC, cai neste moderado
_DEFAULT_INTENSITY = 0.65

# TRIMP de Banister: fator = %FCR × k × e^(c·%FCR) — a exponencial dá muito
# mais peso ao esforço forte que o linear. Coeficientes por sexo (Banister).
_BANISTER = {
    "M": (0.64, 1.92),
    "F": (0.86, 1.67),
}


class TrainingLoadAnalyzer:

    @staticmethod
    def analyze(
        history: TrainingHistory,
        reference_date: date | None = None,
        resting_hr: int | None = None,
        max_hr: int | None = None,
        sex: str | None = None,
    ) -> TrainingLoad:
        """Carga aguda vs crônica + ACWR. Com `resting_hr` E `max_hr`, cada
        sessão é ponderada por INTENSIDADE (TRIMP de Banister quando o `sex` é
        conhecido — exponencial por sexo; senão %FCR linear). Sem FC repouso/
        máx, cai na duração pura. O ACWR é razão, então a unidade não muda o
        veredito — o que muda é o peso relativo de treino forte vs leve."""

        ref = reference_date or today_local()

        # carga por dia — ponderada por intensidade quando dá, senão duração
        per_day = TrainingLoadAnalyzer._load_per_day(
            history, resting_hr, max_hr, sex
        )

        acute = TrainingLoadAnalyzer._window_sum(per_day, ref, _ACUTE_DAYS)

        chronic_total = TrainingLoadAnalyzer._window_sum(
            per_day, ref, _CHRONIC_DAYS
        )

        # crônica = média SEMANAL nos 28 dias (pra o ACWR comparar maçã com
        # maçã: aguda de 7 dias contra a média de 7 dias do último mês)
        chronic = round(chronic_total / (_CHRONIC_DAYS / 7), 1)

        acute = round(acute, 1)

        days_of_history = TrainingLoadAnalyzer._history_span(per_day, ref)

        acwr = (
            round(acute / chronic, 2)
            if chronic > 0
            else None
        )

        status = TrainingLoadAnalyzer._status(acwr, days_of_history)

        return TrainingLoad(
            acute_load=acute,
            chronic_load=chronic,
            acwr=acwr,
            status=status,
            days_of_history=days_of_history,
            weekly_loads=TrainingLoadAnalyzer._weekly_loads(per_day, ref),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _intensity_factor(hrr: float, sex: str | None) -> float:
        """Peso de intensidade da sessão a partir do %FCR. Com sexo conhecido,
        TRIMP de Banister (exponencial); senão, %FCR linear."""

        coeffs = _BANISTER.get((sex or "").upper()[:1])

        if coeffs is None:

            return hrr

        k, c = coeffs

        return hrr * k * math.exp(c * hrr)

    @staticmethod
    def _load_per_day(
        history: TrainingHistory,
        resting_hr: int | None,
        max_hr: int | None,
        sex: str | None,
    ) -> dict[date, float]:
        """Carga somada por dia. Com FC repouso + máx válidas, cada sessão é
        ponderada por intensidade (Banister se souber o sexo, senão %FCR
        linear); sem FC repouso/máx, duração pura (v1)."""

        intensity_mode = (
            resting_hr is not None
            and max_hr is not None
            and max_hr > resting_hr
        )

        # (dia, minutos, fator) — fator None quando a sessão não tem FC
        sessions: list[tuple[date, float, float | None]] = []

        for activity in history.activities:

            minutes = (activity.moving_time or 0) / 60

            if minutes <= 0:

                continue

            factor = None

            if intensity_mode and activity.average_heartrate:

                hrr = (activity.average_heartrate - resting_hr) / (
                    max_hr - resting_hr
                )

                hrr = min(1.0, max(0.0, hrr))

                factor = TrainingLoadAnalyzer._intensity_factor(hrr, sex)

            sessions.append((activity.start_date.date(), minutes, factor))

        per_day: dict[date, float] = defaultdict(float)

        if not intensity_mode:

            for day, minutes, _ in sessions:

                per_day[day] += minutes

            return per_day

        # sessão sem FC (rara) herda a mediana de intensidade do próprio atleta
        known = [f for _, _, f in sessions if f is not None]

        fallback = statistics.median(known) if known else _DEFAULT_INTENSITY

        for day, minutes, factor in sessions:

            per_day[day] += minutes * (factor if factor is not None else fallback)

        return per_day

    @staticmethod
    def _window_sum(
        per_day: dict[date, float],
        ref: date,
        days: int,
    ) -> float:
        """Soma a carga na janela [ref-(days-1) .. ref] inclusive."""

        start = ref - timedelta(days=days - 1)

        return sum(
            load
            for day, load in per_day.items()
            if start <= day <= ref
        )

    @staticmethod
    def _history_span(per_day: dict[date, float], ref: date) -> int:
        """Dias entre o treino mais antigo (até 28d atrás) e a referência —
        pra saber se há baseline suficiente pro veredito."""

        days_with_load = [
            day
            for day in per_day
            if ref - timedelta(days=_CHRONIC_DAYS - 1) <= day <= ref
        ]

        if not days_with_load:

            return 0

        return (ref - min(days_with_load)).days + 1

    @staticmethod
    def _weekly_loads(per_day: dict[date, float], ref: date) -> list[float]:
        """Carga de cada uma das últimas 4 semanas (antigo→novo), pra a
        camada 3 narrar a tendência (rampa/estável/queda)."""

        weeks: list[float] = []

        for w in range(3, -1, -1):

            end = ref - timedelta(days=7 * w)

            start = end - timedelta(days=6)

            weeks.append(
                round(
                    sum(
                        load
                        for day, load in per_day.items()
                        if start <= day <= end
                    ),
                    1,
                )
            )

        return weeks

    @staticmethod
    def _status(acwr: float | None, days_of_history: int) -> str:

        if acwr is None or days_of_history < _MIN_HISTORY_DAYS:

            return LOAD_INSUFFICIENT

        if acwr < ACWR_DETRAINING:

            return LOAD_DETRAINING

        if acwr <= ACWR_OPTIMAL_MAX:

            return LOAD_OPTIMAL

        if acwr <= ACWR_CAUTION_MAX:

            return LOAD_CAUTION

        return LOAD_HIGH
