from __future__ import annotations

from app.domain.entities.activity import Activity


class StatisticsEngine:

    @staticmethod
    def build(activities: list[Activity]) -> dict:

        if not activities:
            return {}

        total_distance = sum(a.distance for a in activities)

        total_time = sum(a.elapsed_time for a in activities)

        hrs = [
            a.average_heartrate
            for a in activities
            if a.average_heartrate
        ]

        longest = max(a.distance for a in activities)

        avg_hr = round(sum(hrs) / len(hrs), 1) if hrs else None

        avg_pace_seconds = total_time / (total_distance / 1000)

        minutes = int(avg_pace_seconds // 60)
        seconds = int(avg_pace_seconds % 60)

        return {
            "total_runs": len(activities),
            "total_distance_km": round(total_distance / 1000, 2),
            "average_pace": f"{minutes}:{seconds:02d}/km",
            "average_hr": avg_hr,
            "longest_run_km": round(longest / 1000, 2),
        }