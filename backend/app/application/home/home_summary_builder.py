from __future__ import annotations

from datetime import timedelta

from app.core.clock import now_local
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.race_prediction_repository import (
    RacePredictionRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.shoe_repository import ShoeRepository
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

_WEEK_EN = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_DAY_PT = {
    "Monday": "Seg",
    "Tuesday": "Ter",
    "Wednesday": "Qua",
    "Thursday": "Qui",
    "Friday": "Sex",
    "Saturday": "Sáb",
    "Sunday": "Dom",
}


def _kind(workout_type: str) -> str:
    """Rótulo de cor pro tipo de treino (tiro/rodagem/longão)."""

    t = (workout_type or "").lower()

    if any(w in t for w in ("tiro", "interval", "fartlek", "limiar", "tempo")):

        return "tiro"

    if "long" in t:

        return "long"

    return "rod"


class HomeSummaryBuilder:
    """Monta o resumo da HOME do atleta a partir de leituras BARATAS e
    determinísticas — nada de IA, nada de gerar plano, nada de efeito colateral
    (é um carregamento de tela). Cada bloco é best-effort: se uma fonte falha ou
    está vazia, aquele pedaço vem None e a home esconde a seção — nunca quebra."""

    @staticmethod
    def build(profile: str) -> dict:

        now = now_local()
        today_en = now.strftime("%A")

        runner = RunnerProfileRepository().load(profile)

        plan = HomeSummaryBuilder._safe(
            lambda: WeeklyPlanRepository().load(profile)
        )

        sessions = {s.day: s for s in plan.sessions} if plan else {}

        return {
            "athlete": {"name": runner.name, "goal": runner.goal},
            "today": HomeSummaryBuilder._today(sessions.get(today_en), now),
            "week": HomeSummaryBuilder._week(sessions, today_en, now),
            "body": HomeSummaryBuilder._safe(
                lambda: HomeSummaryBuilder._body(profile)
            ),
            "fitness": HomeSummaryBuilder._safe(
                lambda: HomeSummaryBuilder._fitness(profile)
            ),
            "shoe": HomeSummaryBuilder._safe(
                lambda: HomeSummaryBuilder._shoe(profile)
            ),
        }

    # ---- blocos ----

    @staticmethod
    def _today(session, now) -> dict:

        base = {
            "weekday_pt": _DAY_PT.get(now.strftime("%A"), ""),
            "date_label": now.strftime("%d/%m"),
        }

        if session is None:

            base["session"] = None

            return base

        base["session"] = {
            "workout_type": session.workout_type,
            "objective": session.objective,
            "distance_km": session.planned_distance_km,
            "duration_min": session.planned_duration_minutes,
            "pace_min": session.target_pace_min,
            "pace_max": session.target_pace_max,
            "kind": _kind(session.workout_type),
            "steps": [
                HomeSummaryBuilder._step(s) for s in (session.steps or [])
            ],
        }

        return base

    @staticmethod
    def _step(step) -> dict:

        out = {
            "kind": step.kind,
            "distance_m": step.distance_m,
            "duration_sec": step.duration_sec,
            "pace_min": step.pace_min,
            "pace_max": step.pace_max,
            "reps": step.reps,
        }

        if step.kind == "repeat":

            out["steps"] = [
                HomeSummaryBuilder._step(c) for c in (step.steps or [])
            ]

        return out

    @staticmethod
    def _week(sessions: dict, today_en: str, now) -> list[dict]:

        monday = (now - timedelta(days=now.weekday())).date()

        week = []

        for i, day_en in enumerate(_WEEK_EN):

            s = sessions.get(day_en)

            week.append(
                {
                    "day_pt": _DAY_PT[day_en],
                    "date_num": (monday + timedelta(days=i)).day,
                    "workout_type": s.workout_type if s else None,
                    "kind": _kind(s.workout_type) if s else None,
                    "is_today": day_en == today_en,
                }
            )

        return week

    @staticmethod
    def _body(profile: str) -> dict | None:

        h = GarminHealthRepository().latest(profile)

        if h is None or not h.has_data:

            return None

        return {
            "readiness_score": h.readiness_score,
            "readiness_level": h.readiness_level,
            "sleep_hours": h.sleep_hours,
            "resting_hr": h.resting_hr,
            "respiration_sleep_avg": h.respiration_sleep_avg,
            "body_battery_at_wake": h.body_battery_at_wake,
            "steps": h.steps,
            "active_calories": h.active_calories,
            "spo2_sleep_avg": h.spo2_sleep_avg,
            "training_status": h.training_status,
            "date": h.date,
        }

    @staticmethod
    def _fitness(profile: str) -> dict | None:

        health = GarminHealthRepository().latest(profile)

        vo2max = health.vo2max if health else None

        pred = RacePredictionRepository().load(profile)

        proj_10k = pred.time_10k if (pred and pred.has_data) else None

        if vo2max is None and proj_10k is None:

            return None

        return {
            "vo2max": vo2max,
            "projection_10k": proj_10k,
            "projection_5k": pred.time_5k if (pred and pred.has_data) else None,
            "projection_half": (
                pred.time_half if (pred and pred.has_data) else None
            ),
        }

    @staticmethod
    def _shoe(profile: str) -> dict | None:

        book = ShoeRepository().load(profile)

        active = [s for s in book.shoes if not s.retired]

        if not active:

            return None

        # o par em uso: o default, senão o de maior rodagem
        shoe = next(
            (s for s in active if s.is_default),
            max(active, key=lambda s: s.total_km),
        )

        threshold = shoe.alert_threshold_km or 1

        return {
            "name": shoe.display_name,
            "total_km": shoe.total_km,
            "alert_threshold_km": shoe.alert_threshold_km,
            "pct": min(100, round(shoe.total_km / threshold * 100)),
            "remaining_km": round(max(0.0, shoe.alert_threshold_km - shoe.total_km), 1),
        }

    # ---- util ----

    @staticmethod
    def _safe(fn):
        """Roda o bloco; qualquer falha vira None (a home esconde a seção)."""

        try:

            return fn()

        except Exception as e:

            print(f"[home] bloco falhou: {e}")

            return None
