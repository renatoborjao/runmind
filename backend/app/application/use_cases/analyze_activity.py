from __future__ import annotations

from app.application.services.metrics_engine import MetricsEngine
from app.domain.entities.activity import Activity


class AnalyzeActivity:

    @staticmethod
    def execute(activity: Activity) -> dict:

        return {
            "activity": {
                "id": activity.id,
                "name": activity.name,
                "sport": activity.sport,
                "start_date": activity.start_date,
            },
            "metrics": {
                "distance_km": MetricsEngine.distance_km(activity),
                "duration_minutes": MetricsEngine.duration_minutes(activity),
                "pace": MetricsEngine.pace(activity),
                "speed_kmh": MetricsEngine.speed(activity),
                "average_hr": activity.average_heartrate,
                "max_hr": activity.max_heartrate,
                "elevation_gain": activity.elevation_gain,
            },
            "analysis": {
                "summary": "Primeira versão do Coach Engine."
            }
        }