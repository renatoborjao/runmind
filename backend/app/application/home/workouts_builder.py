from __future__ import annotations

from datetime import date, timedelta

from app.application.home.home_summary_builder import (
    _DAY_PT,
    _WEEK_EN,
    _kind,
    HomeSummaryBuilder,
    planned_km,
)
from app.core.clock import now_local
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WorkoutsBuilder:
    """Todos os treinos da SEMANA (com detalhe/passos) + a prova-alvo, pra a aba
    de calendário/lista do app. Leituras baratas (plano salvo + perfil), sem IA
    nem geração."""

    @staticmethod
    def build(profile: str) -> dict:

        now = now_local()
        today_date = now.date()

        plan = HomeSummaryBuilder._safe(
            lambda: WeeklyPlanRepository().load(profile)
        )

        sessions = {s.day: s for s in plan.sessions} if plan else {}

        # ancora no week_start DO PLANO (pode ser a próxima semana), não na
        # segunda do calendário atual — senão os treinos caem na semana errada.
        monday = HomeSummaryBuilder._week_monday(plan, now)

        week = []

        for i, day_en in enumerate(_WEEK_EN):

            day_date = monday + timedelta(days=i)

            s = sessions.get(day_en)

            week.append(
                {
                    "day_en": day_en,
                    "day_pt": _DAY_PT[day_en],
                    "date_iso": day_date.isoformat(),
                    "date_num": day_date.day,
                    "is_today": day_date == today_date,
                    "is_past": day_date < today_date,
                    "session": WorkoutsBuilder._session(s),
                }
            )

        return {
            "week": week,
            "race": WorkoutsBuilder._safe_race(profile, now.date()),
        }

    @staticmethod
    def _session(s) -> dict | None:

        if s is None:

            return None

        return {
            "workout_type": s.workout_type,
            "objective": s.objective,
            "distance_km": planned_km(s),
            "duration_min": s.planned_duration_minutes,
            "pace_min": s.target_pace_min,
            "pace_max": s.target_pace_max,
            "kind": _kind(s.workout_type),
            "steps": [HomeSummaryBuilder._step(st) for st in (s.steps or [])],
        }

    @staticmethod
    def _safe_race(profile: str, today: date) -> dict | None:

        try:

            runner = RunnerProfileRepository().load(profile)

            if not runner.target_race or not runner.race_date:

                return None

            race_day = date.fromisoformat(runner.race_date)

            return {
                "name": runner.target_race,
                "date_iso": runner.race_date,
                "target_time": runner.target_time,
                "days_until": (race_day - today).days,
            }

        except Exception:

            return None
