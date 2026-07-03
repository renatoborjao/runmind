from app.application.services.metrics_engine import MetricsEngine
from app.domain.entities.activity import Activity

from .activity import ActivityResponse


def to_activity_response(activity: Activity) -> ActivityResponse:

    return ActivityResponse(

        id=activity.id,

        name=activity.name,

        sport=activity.sport,

        distance_km=MetricsEngine.distance_km(activity),

        duration_minutes=MetricsEngine.duration_minutes(activity),

        pace=MetricsEngine.pace(activity),

        average_hr=activity.average_heartrate,

        max_hr=activity.max_heartrate,

        elevation_gain=activity.elevation_gain,
    )