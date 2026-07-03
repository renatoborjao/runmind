from datetime import date

from app.infrastructure.integrations.strava.mapper import StravaMapper


def _payload(**overrides) -> dict:

    defaults = {
        "id": 1,
        "name": "Corrida noturna",
        "sport_type": "Run",
        # sábado 21h30 no Brasil = domingo 00h30 em UTC
        "start_date": "2026-07-05T00:30:00Z",
        "start_date_local": "2026-07-04T21:30:00Z",
        "timezone": "(GMT-03:00) America/Sao_Paulo",
        "distance": 8000.0,
        "moving_time": 2700,
        "elapsed_time": 2800,
        "average_speed": 2.96,
        "max_speed": 4.0,
        "total_elevation_gain": 40.0,
        "kudos_count": 0,
        "comment_count": 0,
    }

    defaults.update(overrides)

    return defaults


def test_uses_local_start_date_not_utc():

    activity = StravaMapper.to_activity(_payload())

    # a corrida aconteceu no sábado (hora de parede do atleta),
    # não no domingo (data UTC)
    assert activity.start_date.date() == date(2026, 7, 4)


def test_falls_back_to_utc_start_date_when_local_missing():

    payload = _payload()

    del payload["start_date_local"]

    activity = StravaMapper.to_activity(payload)

    assert activity.start_date.date() == date(2026, 7, 5)
