from pydantic import BaseModel


class ActivityResponse(BaseModel):

    id: int
    name: str
    sport: str

    distance_km: float

    duration_minutes: float

    pace: str

    average_hr: float | None

    max_hr: float | None

    elevation_gain: float