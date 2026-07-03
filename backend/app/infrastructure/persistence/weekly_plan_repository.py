import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


class WeeklyPlanRepository:

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "plans"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> TrainingPlan | None:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return None

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        sessions = [
            PlannedSession(**session)
            for session in data["sessions"]
        ]

        return TrainingPlan(
            athlete_name=data["athlete_name"],
            objective=data["objective"],
            phase=data["phase"],
            weekly_volume=data["weekly_volume"],
            running_days=data["running_days"],
            week_start=date.fromisoformat(data["week_start"]),
            sessions=sessions,
            # planos salvos antes do campo existir são do RunMind
            source=data.get("source", "runmind"),
        )

    def save(
        self,
        profile: str,
        plan: TrainingPlan,
    ) -> None:

        data = {
            "athlete_name": plan.athlete_name,
            "objective": plan.objective,
            "phase": plan.phase,
            "weekly_volume": plan.weekly_volume,
            "running_days": plan.running_days,
            "week_start": plan.week_start.isoformat(),
            "source": plan.source,
            "sessions": [
                asdict(session)
                for session in plan.sessions
            ],
        }

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )
