from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from app.domain.entities.activity import Activity

WeekKey = tuple[int, int]


def activity_date(activity: Activity) -> date:

    start = activity.start_date

    if not isinstance(start, datetime):

        start = datetime.fromisoformat(
            str(start).replace("Z", "+00:00")
        )

    return start.date()


def group_by_week(
    activities: list[Activity],
) -> dict[WeekKey, list[Activity]]:

    buckets: dict[WeekKey, list[Activity]] = defaultdict(list)

    for activity in activities:

        week_key = activity_date(activity).isocalendar()[:2]

        buckets[week_key].append(activity)

    return buckets


def last_week_keys(
    reference_date: date,
    weeks: int,
) -> list[WeekKey]:
    """Chaves ISO das últimas `weeks` semanas, da mais antiga
    para a mais recente, incluindo a semana da data de referência."""

    return [
        (reference_date - timedelta(weeks=i)).isocalendar()[:2]
        for i in range(weeks - 1, -1, -1)
    ]


def week_start(week_key: WeekKey) -> date:

    year, week = week_key

    return date.fromisocalendar(year, week, 1)


def week_stats(activities: list[Activity]) -> dict:

    distance_km = sum(
        activity.distance for activity in activities
    ) / 1000

    moving_minutes = sum(
        activity.moving_time for activity in activities
    ) / 60

    avg_pace_min_km = (
        round(moving_minutes / distance_km, 2)
        if distance_km > 0
        else None
    )

    heart_rates = [
        activity.average_heartrate
        for activity in activities
        if activity.average_heartrate
    ]

    avg_hr = (
        round(sum(heart_rates) / len(heart_rates), 1)
        if heart_rates
        else None
    )

    elevation_gain = sum(
        activity.elevation_gain for activity in activities
    )

    return {
        "runs": len(activities),
        "distance_km": round(distance_km, 1),
        "avg_pace_min_km": avg_pace_min_km,
        "avg_hr": avg_hr,
        "elevation_gain": round(elevation_gain, 1),
    }
