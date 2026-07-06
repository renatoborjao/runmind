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

        week_start = WeeklyPlanService._week_start(today_local())

        repository = WeeklyPlanRepository()

        existing = repository.load(profile)

        # mais um print do plano da MESMA semana (treinador manda o plano em
        # várias imagens): mescla por dia, novo print substitui o dia. Plano
        # de outra semana (ou primeiro print) começa do zero.
        if (
            existing is not None
            and existing.source == EXTERNAL_SOURCE
            and existing.week_start == week_start
        ):

            planned = ExternalPlanService._merge_planned(
                existing.sessions,
                planned,
            )

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
            week_start=week_start,
            sessions=planned,
            source=EXTERNAL_SOURCE,
        )

        repository.save(profile, plan)

        return plan

    @staticmethod
    def _merge_planned(
        existing: list[PlannedSession],
        incoming: list[PlannedSession],
    ) -> list[PlannedSession]:
        """Junta sessões de vários prints da mesma semana: dedup por dia,
        a sessão nova substitui a antiga daquele dia."""

        merged: list[PlannedSession] = []

        index_by_day: dict[str, int] = {}

        for session in list(existing) + list(incoming):

            if session.day in index_by_day:

                merged[index_by_day[session.day]] = session

                continue

            index_by_day[session.day] = len(merged)

            merged.append(session)

        return merged

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
