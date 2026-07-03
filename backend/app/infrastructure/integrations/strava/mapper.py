from __future__ import annotations

from datetime import datetime

from app.domain.entities.activity import Activity


class StravaMapper:

    @staticmethod
    def to_activity(data: dict) -> Activity:

        start = data.get("start_latlng") or [None, None]
        end = data.get("end_latlng") or [None, None]

        return Activity(
            id=data["id"],
            name=data["name"],
            sport=data["sport_type"],
            start_date=datetime.fromisoformat(
                data["start_date"].replace("Z", "+00:00")
            ),
            timezone=data["timezone"],
            distance=data["distance"],
            moving_time=data["moving_time"],
            elapsed_time=data["elapsed_time"],
            average_speed=data["average_speed"],
            max_speed=data["max_speed"],
            average_heartrate=data.get("average_heartrate"),
            max_heartrate=data.get("max_heartrate"),
            elevation_gain=data["total_elevation_gain"],
            elevation_high=data.get("elev_high"),
            elevation_low=data.get("elev_low"),
            start_latitude=start[0],
            start_longitude=start[1],
            end_latitude=end[0],
            end_longitude=end[1],
            kudos=data["kudos_count"],
            comments=data["comment_count"],
            suffer_score=data.get("suffer_score"),
            raw=data,
        )