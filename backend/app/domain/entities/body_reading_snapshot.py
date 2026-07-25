from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

# --- movimento da trajetória: como o corpo está HOJE vs a última leitura ---
TRAJ_FIRST = "FIRST"            # primeira leitura — nada com que comparar
TRAJ_IMPROVED = "IMPROVED"      # saiu de um estado pior (ex.: alerta -> ok)
TRAJ_WORSENED = "WORSENED"      # entrou num estado pior (ex.: ok -> alerta)
TRAJ_PERSISTING = "PERSISTING"  # segue em alerta pela 2ª+ leitura seguida
TRAJ_STEADY = "STEADY"          # sem mudança relevante


@dataclass(slots=True)
class BodyReadingSnapshot:
    """Retrato ENXUTO de uma leitura do corpo, guardado pra a leitura seguinte
    saber de onde o atleta veio (foto -> filme). Só o essencial pra comparar
    estado e narrar a trajetória; o cálculo pesado vive na BodyReading."""

    at: str  # hora local (ISO) em que a leitura foi feita
    body_state: str
    limiter: str | None
    acwr: float | None
    acwr_status: str
    hrv_recent: float | None
    hrv_direction: str
    rhr_recent: int | None
    rhr_direction: str
    sleep_avg_hours: float | None
    short_nights: int
    nights_counted: int

    @property
    def day(self) -> date:
        """Dia (local) da leitura — a série guarda no máximo um snapshot por
        dia (releituras do mesmo dia colapsam)."""

        try:

            return datetime.fromisoformat(self.at).date()

        except (ValueError, TypeError):

            # data ilegível: joga pro passado remoto pra nunca colidir com hoje
            return date.min


@dataclass(slots=True)
class BodyTrajectory:
    """A leitura de HOJE lida à luz das anteriores. É o que transforma uma
    foto ('seu corpo está em alerta') num filme ('3ª leitura seguida assim' /
    'melhorou desde a última'). Dois textos: um pro atleta, um pro cérebro."""

    movement: str                 # TRAJ_* acima
    alert_streak: int             # leituras SEGUIDAS em alerta (inclui a atual)
    previous_state: str | None    # estado da última leitura (None se 1ª)
    athlete_note: str = ""        # frase pro atleta ("" quando nada a dizer)
    fact: str = ""                # frase pro cérebro coach ("" quando 1ª)

    @property
    def has_note(self) -> bool:

        return bool(self.athlete_note)
