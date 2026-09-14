from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

from app.application.home.home_summary_builder import _DAY_PT, _kind, planned_km
from app.core.clock import now_local
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.recorded_run_repository import (
    RecordedRunRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    s = (sport or "").lower()

    return any(h in s for h in _RUN_HINT)


def _is_ours(name: str) -> bool:
    """Treino NOSSO: o nome no Strava foi renomeado pro nome do plano (Ritmind)."""

    n = (name or "").lower()

    return "ritmind" in n or "runmind" in n


def _run_date(r: dict) -> date | None:
    """Data de uma corrida gravada no app (started_at; cai no saved_at)."""

    for key in ("started_at", "saved_at"):

        v = r.get(key)

        if v:

            try:

                return date.fromisoformat(str(v)[:10])

            except ValueError:

                continue

    return None


def _pace_str(distance_m: float, moving_time_s: int) -> str | None:

    km = distance_m / 1000

    if km <= 0 or not moving_time_s:

        return None

    p = (moving_time_s / 60) / km

    return f"{int(p)}:{int(round((p % 1) * 60)):02d}"


class CalendarBuilder:
    """Calendário do atleta: treinos EXECUTADOS (arquivo local) por mês + os
    PLANEJADOS futuros (plano da semana) + prova. E o detalhe de um dia com
    planejado × executado (comparação determinística; a análise IA do treino não
    é persistida). Tudo leitura barata, sem IA."""

    @staticmethod
    def month(profile: str, year: int, month: int) -> dict:

        first = date(year, month, 1)
        last = date(year, month, _cal.monthrange(year, month)[1])
        today = now_local().date()

        # executados no mês (arquivo local, deduplicado)
        executed = []

        for a in ActivityArchiveRepository().load_activities(profile):

            d = a.start_date.date()

            if first <= d <= last and _is_run(a.sport):

                executed.append(
                    {
                        "date_iso": d.isoformat(),
                        "km": round(a.distance / 1000, 1),
                        "pace": _pace_str(a.distance, a.moving_time),
                        "duration_min": round(a.moving_time / 60),
                        "name": a.name,
                        "kind": _kind(a.name),
                        "is_ours": _is_ours(a.name),
                    }
                )

        executed_dates = {e["date_iso"] for e in executed}

        # corridas gravadas no APP (GPS) — pintam o dia SÓ quando não há um treino
        # arquivado (Strava/Garmin) na mesma data, pra não contar 2x quem
        # sincroniza. Ver [[project_independencia_strava]].
        for r in CalendarBuilder._safe(
            lambda: RecordedRunRepository().load(profile)
        ) or []:

            d = _run_date(r)

            if d is None or not (first <= d <= last):

                continue

            if d.isoformat() in executed_dates:

                continue

            executed.append(
                {
                    "date_iso": d.isoformat(),
                    "km": round((r.get("distance_m") or 0) / 1000, 1),
                    "pace": r.get("avg_pace"),
                    "duration_min": round((r.get("duration_s") or 0) / 60),
                    "name": "Corrida no app",
                    "kind": "rod",
                    "is_ours": False,
                    "source": "app",
                }
            )

            executed_dates.add(d.isoformat())

        # planejados FUTUROS (>= hoje) do plano atual que caem no mês — dias
        # passados já mostram o executado, não faz sentido "planejar" o passado
        planned = []

        plan = CalendarBuilder._safe(
            lambda: WeeklyPlanRepository().load(profile)
        )

        if plan:

            by_day = {s.day: s for s in plan.sessions}

            for i in range(7):

                d = plan.week_start + timedelta(days=i)

                if not (first <= d <= last) or d < today:

                    continue

                if d.isoformat() in executed_dates:

                    continue

                day_en = d.strftime("%A")

                s = by_day.get(day_en)

                if s:

                    planned.append(
                        {
                            "date_iso": d.isoformat(),
                            "day_en": day_en,
                            "workout_type": s.workout_type,
                            "kind": _kind(s.workout_type),
                        }
                    )

        return {
            "month": f"{year}-{month:02d}",
            "executed": executed,
            "planned": planned,
            "race": CalendarBuilder._race(profile, today),
        }

    @staticmethod
    def day(profile: str, date_iso: str) -> dict:
        """Detalhe de um dia: executado (o que foi feito) + planejado (o que o
        plano previa naquele dia — do plano atual OU do histórico de planos)."""

        d = date.fromisoformat(date_iso)

        executed = None

        for a in ActivityArchiveRepository().load_activities(profile):

            if a.start_date.date() == d and _is_run(a.sport):

                executed = {
                    "km": round(a.distance / 1000, 1),
                    "pace": _pace_str(a.distance, a.moving_time),
                    "duration_min": round(a.moving_time / 60),
                    "avg_hr": int(a.average_heartrate) if a.average_heartrate else None,
                    "elevation_gain": round(a.elevation_gain) if a.elevation_gain else None,
                    "name": a.name,
                    "is_ours": _is_ours(a.name),
                }

                break

        # sem treino arquivado no dia? usa a corrida gravada no app, se houver
        if executed is None:

            for r in CalendarBuilder._safe(
                lambda: RecordedRunRepository().load(profile)
            ) or []:

                if _run_date(r) == d:

                    executed = {
                        "km": round((r.get("distance_m") or 0) / 1000, 1),
                        "pace": r.get("avg_pace"),
                        "duration_min": round((r.get("duration_s") or 0) / 60),
                        "avg_hr": None,
                        "elevation_gain": None,
                        "name": "Corrida no app",
                        "is_ours": False,
                    }

                    break

        planned = CalendarBuilder._planned_for(profile, d)

        return {
            "date_iso": date_iso,
            "day_pt": _DAY_PT.get(d.strftime("%A"), ""),
            "executed": executed,
            "planned": planned,
        }

    # ---- helpers ----

    @staticmethod
    def _planned_for(profile: str, d: date) -> dict | None:
        """A sessão planejada pra ESSE dia — procura no plano atual e no
        histórico de planos (semana que contém o dia)."""

        repo = WeeklyPlanRepository()

        plans = []

        current = CalendarBuilder._safe(lambda: repo.load(profile))

        if current:

            plans.append(current)

        plans += CalendarBuilder._safe(lambda: repo.history(profile)) or []

        for p in plans:

            if p.week_start <= d <= p.week_start + timedelta(days=6):

                s = {sess.day: sess for sess in p.sessions}.get(d.strftime("%A"))

                if s:

                    return {
                        "workout_type": s.workout_type,
                        "distance_km": planned_km(s),
                        "pace_min": s.target_pace_min,
                        "pace_max": s.target_pace_max,
                        "kind": _kind(s.workout_type),
                    }

        return None

    @staticmethod
    def _race(profile: str, today: date) -> dict | None:

        try:

            runner = RunnerProfileRepository().load(profile)

            if not runner.target_race or not runner.race_date:

                return None

            race_day = date.fromisoformat(runner.race_date)

            return {
                "name": runner.target_race,
                "date_iso": runner.race_date,
                "days_until": (race_day - today).days,
            }

        except Exception:

            return None

    @staticmethod
    def _safe(fn):

        try:

            return fn()

        except Exception as e:

            print(f"[calendar] bloco falhou: {e}")

            return None
