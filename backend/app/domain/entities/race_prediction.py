from __future__ import annotations

from dataclasses import dataclass


def _fmt(seconds: int | None) -> str | None:
    """Segundos -> tempo de prova legível: M:SS abaixo de 1h, H:MM:SS acima."""

    if not seconds or seconds <= 0:

        return None

    total = int(round(seconds))

    h, rest = divmod(total, 3600)

    m, s = divmod(rest, 60)

    if h:

        return f"{h}:{m:02d}:{s:02d}"

    return f"{m}:{s:02d}"


@dataclass(slots=True)
class RacePrediction:
    """Previsão de tempo de prova que a PRÓPRIA Garmin calcula (5K/10K/meia/
    maratona), a partir do VO₂máx + histórico de treino do atleta. Estado
    ATUAL (muda esporádico), não série diária — vale até o relógio recalcular.

    Serve a dois donos: o atleta (o que o corpo entrega hoje, meta visível) e
    o plano (calibra realismo/periodização — não prescrever um alvo que a
    projeção não sustenta). Tempos em SEGUNDOS; None quando o device não prevê
    aquela distância. Puro/determinístico — o writer só narra."""

    date: str | None = None  # calendarDate da projeção (YYYY-MM-DD)

    time_5k_sec: int | None = None
    time_10k_sec: int | None = None
    time_half_sec: int | None = None
    time_marathon_sec: int | None = None

    @property
    def has_data(self) -> bool:

        return any(
            v is not None
            for v in (
                self.time_5k_sec,
                self.time_10k_sec,
                self.time_half_sec,
                self.time_marathon_sec,
            )
        )

    @property
    def time_5k(self) -> str | None:

        return _fmt(self.time_5k_sec)

    @property
    def time_10k(self) -> str | None:

        return _fmt(self.time_10k_sec)

    @property
    def time_half(self) -> str | None:

        return _fmt(self.time_half_sec)

    @property
    def time_marathon(self) -> str | None:

        return _fmt(self.time_marathon_sec)

    def to_dict(self) -> dict:

        return {
            "date": self.date,
            "time_5k_sec": self.time_5k_sec,
            "time_10k_sec": self.time_10k_sec,
            "time_half_sec": self.time_half_sec,
            "time_marathon_sec": self.time_marathon_sec,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RacePrediction":

        fields = cls.__dataclass_fields__

        return cls(**{k: v for k, v in (data or {}).items() if k in fields})
