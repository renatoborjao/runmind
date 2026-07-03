from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.activity import Activity


@dataclass
class TrainingHistory:

    activities: list[Activity]

    @property
    def total_runs(self) -> int:
        return len(self.activities)

    @property
    def total_distance(self) -> float:
        return sum(activity.distance for activity in self.activities)

    @property
    def total_time(self) -> int:
        return sum(activity.elapsed_time for activity in self.activities)

    @property
    def average_hr(self) -> float | None:

        hrs = [
            activity.average_heartrate
            for activity in self.activities
            if activity.average_heartrate
        ]

        if not hrs:
            return None

        return round(sum(hrs) / len(hrs), 1)

    @property
    def longest_run(self) -> Activity | None:

        if not self.activities:
            return None

        return max(
            self.activities,
            key=lambda activity: activity.distance,
        )

    @property
    def latest(self) -> Activity | None:

        if not self.activities:
            return None

        return self.activities[0]

    @property
    def previous(self) -> Activity | None:

        if len(self.activities) < 2:
            return None

        return self.activities[1]