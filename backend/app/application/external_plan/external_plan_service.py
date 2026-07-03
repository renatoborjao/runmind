from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.core.weekdays import WEEKDAYS
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

EXTERNAL_SOURCE = "externo"


class ExternalPlanService:
    """Transforma sessões extraídas do plano do treinador em um
    TrainingPlan acompanhado (nunca ajustado) pelo RunMind."""

    @staticmethod
    def apply(
        profile: str,
        runner: RunnerProfile,
        sessions: list[dict],
    ) -> TrainingPlan | None:

        planned = ExternalPlanService._to_planned_sessions(sessions)

        if not planned:

            return None

        plan = TrainingPlan(
            athlete_name=runner.name,
            objective=runner.goal,
            phase="EXTERNO",
            weekly_volume=round(
                sum(
                    session.planned_distance_km or 0
                    for session in planned
                ),
                1,
            ),
            running_days=[session.day for session in planned],
            week_start=WeeklyPlanService._week_start(today_local()),
            sessions=planned,
            source=EXTERNAL_SOURCE,
        )

        WeeklyPlanRepository().save(profile, plan)

        return plan

    @staticmethod
    def _to_planned_sessions(
        sessions: list[dict],
    ) -> list[PlannedSession]:

        valid_days = set(WEEKDAYS.values())

        planned = []

        for session in sessions:

            day = session.get("day")

            if day not in valid_days:

                continue

            workout_type = (
                session.get("workout_type") or "Treino"
            ).strip()

            distance = session.get("distance_km")

            duration = session.get("duration_minutes")

            if not isinstance(distance, (int, float)):

                distance = None

            if not isinstance(duration, (int, float)):

                duration = None

            # sessão sem distância nem duração não dá pra acompanhar
            if distance is None and duration is None:

                continue

            planned.append(
                PlannedSession(
                    day=day,
                    workout_type=workout_type,
                    objective=(
                        session.get("objective") or workout_type
                    ),
                    planned_distance_km=(
                        round(float(distance), 1)
                        if distance is not None
                        else None
                    ),
                    planned_duration_minutes=(
                        int(duration)
                        if duration is not None
                        else None
                    ),
                    target_pace_min=session.get("pace_min"),
                    target_pace_max=session.get("pace_max"),
                    notes=session.get("notes") or "",
                )
            )

        return planned
