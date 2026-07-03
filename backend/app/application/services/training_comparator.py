from __future__ import annotations

from app.domain.entities.activity import Activity


class TrainingComparator:

    @staticmethod
    def compare(current: Activity, previous: Activity) -> dict:

        pace_delta = current.average_speed - previous.average_speed

        hr_delta = (
            (current.average_heartrate or 0)
            - (previous.average_heartrate or 0)
        )

        distance_delta = current.distance - previous.distance

        return {
            "pace": {
                "current": round(current.average_speed, 2),
                "previous": round(previous.average_speed, 2),
                "delta": round(pace_delta, 2),
            },
            "heart_rate": {
                "current": current.average_heartrate,
                "previous": previous.average_heartrate,
                "delta": round(hr_delta, 1),
            },
            "distance": {
                "current": round(current.distance / 1000, 2),
                "previous": round(previous.distance / 1000, 2),
                "delta": round(distance_delta / 1000, 2),
            },
        }