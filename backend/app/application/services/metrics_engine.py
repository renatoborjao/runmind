from __future__ import annotations

from app.domain.entities.activity import Activity


class MetricsEngine:

    @staticmethod
    def distance_km(activity: Activity) -> float:
        return round(activity.distance / 1000, 2)

    @staticmethod
    def duration_minutes(activity: Activity) -> float:
        return round(activity.moving_time / 60, 1)

    @staticmethod
    def pace(activity: Activity) -> str:

        if activity.distance == 0:
            return "--"

        seconds_per_km = activity.moving_time / (activity.distance / 1000)

        minutes = int(seconds_per_km // 60)

        seconds = int(seconds_per_km % 60)

        return f"{minutes}:{seconds:02d}/km"

    @staticmethod
    def speed(activity: Activity) -> float:

        return round(activity.average_speed * 3.6, 2)