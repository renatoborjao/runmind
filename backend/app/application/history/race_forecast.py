"""A PREVISÃO DE PROVA em FAIXA — onde o histórico real do atleta e o Garmin
discordam, o coach fala de um intervalo, não de um número só.

Caso Leonardo (18/10): no chat o coach disse "a base já está pronta pra fechar os
10 km em 1h com segurança" (o Garmin projeta 56:33) e, no resumo das 19h, "se a prova
fosse hoje: ~1:05:32" (o melhor esforço real dele, por Riegel). Duas respostas do
mesmo coach no mesmo dia, na primeira prova do atleta. Nenhuma das duas fontes é
"a verdade": o Garmin estima pelo VO₂máx e costuma ser otimista (Maurício: 52:38
no Garmin × 58:30 na prova de 19/09); o histórico só mostra o que ele já sustentou.
A faixa diz as duas coisas, rotuladas, e a meta se posiciona dentro dela.

Puro/determinístico (sem IA). Quando as fontes concordam (≤ 4%) ou só uma existe, não
há faixa: segue o número do histórico, como sempre foi."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.planner.race_time_formatter import RaceTimeFormatter
from app.domain.entities.race_prediction import RacePrediction

# fontes dentro desta fração uma da outra = um número só (ruído, não discordância)
AGREE_RATIO = 0.04

# a meta a menos disto (s) da ponta rápida da faixa conta como DENTRO dela: empate
# técnico, não "falta" (João: Garmin 23:03 × meta 23:00)
ON_TARGET_SLACK_SECONDS = 20

# o Garmin só projeta 4 distâncias; pra outra (ex.: 15 km) estimamos por Riegel a
# partir da mais próxima, até esta razão (15/10 = 1.5; 15/21 = 1.4)
MAX_EXTRAPOLATION_RATIO = 2.2

RIEGEL_EXPONENT = 1.06

# (distância km, tolerância km, atributo em segundos)
_STANDARD = (
    (5.0, 0.5, "time_5k_sec"),
    (10.0, 0.5, "time_10k_sec"),
    (21.0975, 0.6, "time_half_sec"),
    (42.195, 0.5, "time_marathon_sec"),
)

HISTORY_LABEL = "seus treinos"
GARMIN_LABEL = "Garmin"


def garmin_seconds_for(
    prediction: RacePrediction | None, distance_km: float | None,
) -> float | None:
    """O tempo que o Garmin projeta pra ESTA distância: o exato quando é uma das 4
    padrão; senão Riegel a partir da mais próxima que ele projetou. None sem dado."""

    if prediction is None or not prediction.has_data or not distance_km:

        return None

    known = [
        (km, getattr(prediction, attr))
        for km, _, attr in _STANDARD
        if getattr(prediction, attr)
    ]

    if not known:

        return None

    for km, tolerance, attr in _STANDARD:

        value = getattr(prediction, attr)

        if value and abs(distance_km - km) <= tolerance:

            return float(value)

    km, seconds = min(
        known,
        key=lambda item: max(item[0], distance_km) / min(item[0], distance_km),
    )

    ratio = max(km, distance_km) / min(km, distance_km)

    if ratio > MAX_EXTRAPOLATION_RATIO:

        return None

    return float(seconds) * (distance_km / km) ** RIEGEL_EXPONENT


@dataclass(slots=True)
class RaceRange:
    """As duas leituras e a faixa entre elas."""

    history_seconds: float
    garmin_seconds: float

    @property
    def low_seconds(self) -> float:

        return min(self.history_seconds, self.garmin_seconds)

    @property
    def high_seconds(self) -> float:

        return max(self.history_seconds, self.garmin_seconds)

    @property
    def low_label(self) -> str:

        return GARMIN_LABEL if self.garmin_seconds <= self.history_seconds else HISTORY_LABEL

    @property
    def high_label(self) -> str:

        return HISTORY_LABEL if self.garmin_seconds <= self.history_seconds else GARMIN_LABEL

    @property
    def is_range(self) -> bool:
        """Só vira faixa quando as duas fontes DISCORDAM de verdade."""

        return (self.high_seconds - self.low_seconds) / self.high_seconds > AGREE_RATIO

    def position_of(self, target_seconds: float) -> str:
        """Onde a meta cai: 'beaten' (mais lenta que a faixa toda — já bateria),
        'inside' (cabe na faixa) ou 'beyond' (mais rápida que a faixa toda)."""

        if target_seconds >= self.high_seconds:

            return "beaten"

        if target_seconds >= self.low_seconds - ON_TARGET_SLACK_SECONDS:

            return "inside"

        return "beyond"

    def to_dict(self) -> dict:

        return {
            "low_seconds": self.low_seconds,
            "high_seconds": self.high_seconds,
            "low_formatted": RaceTimeFormatter.format(self.low_seconds),
            "high_formatted": RaceTimeFormatter.format(self.high_seconds),
            "low_label": self.low_label,
            "high_label": self.high_label,
        }


def build_range(
    history_seconds: float | None, garmin_seconds: float | None,
) -> RaceRange | None:
    """A faixa, ou None quando falta uma fonte."""

    if not history_seconds or not garmin_seconds:

        return None

    return RaceRange(float(history_seconds), float(garmin_seconds))


def range_sentence(forecast: dict) -> str:
    """"entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)" a partir do dict da faixa."""

    return (
        f"entre ~{forecast['low_formatted']} ({forecast['low_label']}) e "
        f"~{forecast['high_formatted']} ({forecast['high_label']})"
    )
