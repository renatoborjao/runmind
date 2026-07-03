from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Activity:
    # Identificação
    id: int
    name: str
    sport: str

    # Datas
    start_date: datetime
    timezone: str

    # Distância e tempo
    distance: float
    moving_time: int
    elapsed_time: int

    # Ritmo
    average_speed: float
    max_speed: float

    # Frequência cardíaca
    average_heartrate: float | None
    max_heartrate: float | None

    # Altimetria
    elevation_gain: float
    elevation_high: float | None
    elevation_low: float | None

    # Localização
    start_latitude: float | None
    start_longitude: float | None
    end_latitude: float | None
    end_longitude: float | None

    # Métricas do Strava
    kudos: int
    comments: int
    suffer_score: int | None

    # JSON original
    raw: dict