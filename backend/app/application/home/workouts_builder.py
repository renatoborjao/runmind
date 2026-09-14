from __future__ import annotations

from datetime import date, timedelta

from app.application.home.home_summary_builder import (
    _DAY_PT,
    _WEEK_EN,
    _kind,
    HomeSummaryBuilder,
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
        today_en = now.strftime("%A")
        monday = (now - timedelta(days=now.weekday())).date()

        plan = HomeSummaryBuilder._safe(
            lambda: WeeklyPlanRepository().load(profile)
        )

        sessions = {s.day: s for s in plan.sessions} if plan else {}

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
                    "is_today": day_en == today_en,
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
            "distance_km": s.planned_distance_km,
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
