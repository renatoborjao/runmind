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

        return self._from_dict(data)

    def save(
        self,
        profile: str,
        plan: TrainingPlan,
    ) -> None:

        data = self._to_dict(plan)

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

        self._append_history(profile, data)

    def history(
        self,
        profile: str,
    ) -> list[TrainingPlan]:
        """Planos de semanas anteriores, em ordem cronológica —
        base para consultas de aderência ao longo do tempo."""

        file = self._history_file(profile)

        if not file.exists():

            return []

        with open(
            file,
            encoding="utf-8",
        ) as f:

            return [
                self._from_dict(data)
                for data in json.load(f)
            ]

    def _append_history(
        self,
        profile: str,
        data: dict,
    ) -> None:
        """Snapshot por semana: ajustes e planos externos atualizados
        substituem a entrada da mesma week_start."""

        file = self._history_file(profile)

        entries = []

        if file.exists():

            with open(
                file,
                encoding="utf-8",
            ) as f:

                entries = json.load(f)

        entries = [
            entry
            for entry in entries
            if entry["week_start"] != data["week_start"]
        ]

        entries.append(data)

        entries.sort(key=lambda entry: entry["week_start"])

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                entries,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _history_file(
        self,
        profile: str,
    ) -> Path:

        history_dir = self.storage / "history"

        history_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        return history_dir / f"{profile}.json"

    @staticmethod
    def _to_dict(
        plan: TrainingPlan,
    ) -> dict:

        return {
            "athlete_name": plan.athlete_name,
            "objective": plan.objective,
            "phase": plan.phase,
            "weekly_volume": plan.weekly_volume,
            "running_days": plan.running_days,
            "week_start": plan.week_start.isoformat(),
            "source": plan.source,
            "is_deload": plan.is_deload,
            "reviewed": plan.reviewed,
            "sessions": [
                asdict(session)
                for session in plan.sessions
            ],
        }

    @staticmethod
    def _from_dict(
        data: dict,
    ) -> TrainingPlan:

        return TrainingPlan(
            athlete_name=data["athlete_name"],
            objective=data["objective"],
            phase=data["phase"],
            weekly_volume=data["weekly_volume"],
            running_days=data["running_days"],
            week_start=date.fromisoformat(data["week_start"]),
            sessions=[
                PlannedSession(**session)
                for session in data["sessions"]
            ],
            source=data.get("source", "runmind"),
            is_deload=data.get("is_deload", False),
            reviewed=data.get("reviewed", False),
        )
