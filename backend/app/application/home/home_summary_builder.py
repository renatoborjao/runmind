from __future__ import annotations

from datetime import date, timedelta

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
from app.domain.entities.workout_step import total_distance_km
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
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


def _is_run(sport: str) -> bool:

    return any(h in (sport or "").lower() for h in ("run", "corrida", "trail"))


def _kind(workout_type: str) -> str:
    """Rótulo de cor pro tipo de treino (tiro/rodagem/longão)."""

    t = (workout_type or "").lower()

    if any(w in t for w in ("tiro", "interval", "fartlek", "limiar", "tempo")):

        return "tiro"

    if "long" in t:

        return "long"

    return "rod"


def planned_km(session) -> float | None:
    """Distância PLANEJADA que o atleta vê — a soma dos BLOCOS (aquecimento +
    principal + recuperações + desaquecimento), que é o número real do treino e
    o que o coach comunica. Cai no campo solto planned_distance_km só quando os
    passos são por tempo/ausentes (soma não confiável)."""

    steps = getattr(session, "steps", None)

    if steps:

        total = total_distance_km(steps)

        if total is not None:

            return total

    return session.planned_distance_km


class HomeSummaryBuilder:
    """Monta o resumo da HOME do atleta a partir de leituras BARATAS e
    determinísticas — nada de IA, nada de gerar plano, nada de efeito colateral
    (é um carregamento de tela). Cada bloco é best-effort: se uma fonte falha ou
    está vazia, aquele pedaço vem None e a home esconde a seção — nunca quebra."""

    @staticmethod
    def build(profile: str) -> dict:

        now = now_local()

        runner = RunnerProfileRepository().load(profile)

        plan = HomeSummaryBuilder._safe(
            lambda: WeeklyPlanRepository().load(profile)
        )

        sessions = {s.day: s for s in plan.sessions} if plan else {}

        # a semana do plano é ancorada no week_start DO PLANO (pode ser a próxima
        # semana — o plano regenera no domingo), NÃO na segunda do calendário
        # atual. Sem isso os treinos caíam na semana errada.
        monday = HomeSummaryBuilder._week_monday(plan, now)

        # dias com corrida REALIZADA (arquivo local) pra pintar de verde
        executed = HomeSummaryBuilder._safe(
            lambda: {
                a.start_date.date().isoformat()
                for a in ActivityArchiveRepository().load_activities(profile)
                if _is_run(a.sport)
            }
        ) or set()

        return {
            "athlete": {"name": runner.name, "goal": runner.goal},
            "today": HomeSummaryBuilder._today(sessions, monday, now),
            "week": HomeSummaryBuilder._week(sessions, monday, now, executed),
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
    def _week_monday(plan, now) -> date:
        """A segunda-feira da semana do plano: do `week_start` gravado no plano
        (fonte de verdade — pode ser a semana que vem); só cai na segunda do
        calendário atual se o plano não disser."""

        ws = getattr(plan, "week_start", None) if plan else None

        # week_start pode vir como date (entidade) ou str (JSON) — aceita os dois
        if isinstance(ws, date):

            return ws

        if isinstance(ws, str):

            try:

                return date.fromisoformat(ws)

            except ValueError:

                pass

        return (now - timedelta(days=now.weekday())).date()

    @staticmethod
    def _session_dict(session) -> dict:

        return {
            "workout_type": session.workout_type,
            "objective": session.objective,
            "distance_km": planned_km(session),
            "duration_min": session.planned_duration_minutes,
            "pace_min": session.target_pace_min,
            "pace_max": session.target_pace_max,
            "kind": _kind(session.workout_type),
            "steps": [
                HomeSummaryBuilder._step(s) for s in (session.steps or [])
            ],
        }

    @staticmethod
    def _today(sessions: dict, monday: date, now) -> dict:
        """O card de destaque: o treino de HOJE quando hoje cai na semana do
        plano; senão (plano é da próxima semana) o PRÓXIMO treino dela. weekday_pt
        /date_label são sempre o dia REAL de hoje (pro cabeçalho)."""

        today_date = now.date()
        week_end = monday + timedelta(days=6)

        base = {
            "weekday_pt": _DAY_PT.get(now.strftime("%A"), ""),
            "date_label": now.strftime("%d/%m"),
            "label": "Treino de hoje",
            "day_en": now.strftime("%A"),
            "session_date_label": None,
            "session": None,
        }

        # hoje está dentro da semana do plano
        if monday <= today_date <= week_end:

            s = sessions.get(now.strftime("%A"))

            if s:

                base["session"] = HomeSummaryBuilder._session_dict(s)

            return base

        # plano é de uma semana futura: mostra o PRÓXIMO treino dela
        if today_date < monday:

            for i, day_en in enumerate(_WEEK_EN):

                s = sessions.get(day_en)

                if s:

                    d = monday + timedelta(days=i)

                    base["label"] = "Próximo treino"
                    base["day_en"] = day_en
                    base["session_date_label"] = (
                        f"{_DAY_PT[day_en]} {d.strftime('%d/%m')}"
                    )
                    base["session"] = HomeSummaryBuilder._session_dict(s)

                    return base

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
    def _week(sessions: dict, monday: date, now, executed: set) -> list[dict]:

        today_date = now.date()

        week = []

        for i, day_en in enumerate(_WEEK_EN):

            d = monday + timedelta(days=i)

            s = sessions.get(day_en)

            week.append(
                {
                    "day_en": day_en,
                    "day_pt": _DAY_PT[day_en],
                    "date_num": d.day,
                    "date_iso": d.isoformat(),
                    "workout_type": s.workout_type if s else None,
                    "distance_km": planned_km(s) if s else None,
                    "kind": _kind(s.workout_type) if s else None,
                    "is_today": d == today_date,
                    "done": d.isoformat() in executed,
                }
            )

        return week

    @staticmethod
    def _body(profile: str) -> dict | None:

        h = GarminHealthRepository().latest(profile)

        if h is None or not h.has_data:

            return None

        # o anel do herói: prontidão do Garmin quando existe; senão a bateria
        # ao acordar (0-100 também) — assim o diferencial aparece com dado real
        # mesmo em relógio que não reporta Training Readiness.
        ring = None

        if h.readiness_score is not None:

            ring = {"value": h.readiness_score, "label": "PRONTIDÃO", "source": "readiness"}

        elif h.body_battery_at_wake is not None:

            ring = {"value": h.body_battery_at_wake, "label": "BATERIA", "source": "battery"}

        return {
            "ring": ring,
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
            "name": shoe.label,
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
