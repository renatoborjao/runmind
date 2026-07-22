"""Radar de sobrecarga (camada 2): calcula a CARGA de treino aguda (7d) vs
crônica (28d) e o ACWR a partir do histórico de atividades — pra QUALQUER
atleta, sem depender do 'training load' que só os relógios Garmin top dão.

Carga = minutos de treino (duração). Puro/testável, sem IO. Não decide nada
sozinho nem fala com o atleta — entrega o retrato pra a camada 3 (síntese)
consumir. Ver [[project_analise_corpo_garmin]]."""

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


class TrainingLoadAnalyzer:

    @staticmethod
    def analyze(
        history: TrainingHistory,
        reference_date: date | None = None,
    ) -> TrainingLoad:

        ref = reference_date or today_local()

        # carga por dia (minutos), só do que caiu na janela crônica
        per_day = TrainingLoadAnalyzer._load_per_day(history)

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
    def _load_per_day(history: TrainingHistory) -> dict[date, float]:
        """Minutos de treino somados por dia (duração = carga na v1)."""

        per_day: dict[date, float] = defaultdict(float)

        for activity in history.activities:

            minutes = (activity.moving_time or 0) / 60

            if minutes > 0:

                per_day[activity.start_date.date()] += minutes

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
