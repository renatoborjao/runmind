"""O PLANO DA SEMANA pra tela Treino do app: o mesmo que o coach manda no chat
("🎯 objetivo · 📦 bloco · 📈 fase · treino a treino"), só que navegável — com o que
já foi feito (planejado × executado) ao lado de cada dia, e as semanas anteriores
(histórico de planos) pra consultar.

Só LEITURA barata (planos salvos + arquivo de corridas): nada de IA, nada de gerar
plano, nenhum efeito colateral — é carregamento de tela. Ver [[project_app_atleta]]."""

from __future__ import annotations

from datetime import date, timedelta

from app.application.home.home_summary_builder import (
    _DAY_PT,
    _WEEK_EN,
    HomeSummaryBuilder,
    _is_run,
    _kind,
    planned_km,
)
from app.application.home.workouts_builder import WorkoutsBuilder
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.weekly_plan_message_formatter import (
    PHASE_LABELS,
    WeeklyPlanMessageFormatter,
)
from app.core.clock import now_local
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WeekPlanBuilder:

    @staticmethod
    def build(profile: str, week_start: str | None = None) -> dict:
        """A semana do plano atual — ou, com `week_start` (segunda, ISO), a de um
        plano ANTERIOR do histórico. `has_plan=False` quando não há plano pra
        essa semana. Sempre devolve `prev_week_start`/`next_week_start` (None =
        sem mais semanas) pra navegação."""

        now = now_local()

        repo = WeeklyPlanRepository()

        current = HomeSummaryBuilder._safe(lambda: repo.load(profile))

        history = HomeSummaryBuilder._safe(lambda: repo.history(profile)) or []

        by_week = {p.week_start.isoformat(): p for p in history}

        if current is not None:

            by_week[current.week_start.isoformat()] = current

        weeks = sorted(by_week)

        current_key = current.week_start.isoformat() if current else None

        chosen = week_start or current_key

        plan = by_week.get(chosen) if chosen else None

        nav = WeekPlanBuilder._nav(weeks, chosen)

        race = WorkoutsBuilder._safe_race(profile, now.date())

        if plan is None:

            return {"has_plan": False, "race": race, **nav}

        monday = plan.week_start

        runs = WeekPlanBuilder._runs_by_date(profile, monday)

        days = [
            WeekPlanBuilder._day(
                plan, i, day_en, monday, now.date(), runs, profile
            )
            for i, day_en in enumerate(_WEEK_EN)
        ]

        return {
            "has_plan": True,
            "week_start": monday.isoformat(),
            "week_end": (monday + timedelta(days=6)).isoformat(),
            "is_current": chosen == current_key,
            "source": getattr(plan, "source", "runmind"),
            "phase": plan.phase,
            "phase_label": PHASE_LABELS.get(plan.phase),
            "objective": getattr(plan, "weekly_objective", "") or "",
            "block_label": getattr(plan, "block_label", None),
            "extra_day_note": getattr(plan, "extra_day_note", None),
            "is_deload": bool(getattr(plan, "is_deload", False)),
            "deload_why": getattr(plan, "deload_why", None),
            "totals": WeekPlanBuilder._totals(days),
            "days": days,
            "race": race,
            **nav,
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _nav(weeks: list[str], chosen: str | None) -> dict:
        """Semana anterior/seguinte que TEM plano (None nas pontas)."""

        if chosen is None or chosen not in weeks:

            return {"prev_week_start": None, "next_week_start": None}

        at = weeks.index(chosen)

        return {
            "prev_week_start": weeks[at - 1] if at > 0 else None,
            "next_week_start": weeks[at + 1] if at < len(weeks) - 1 else None,
        }

    @staticmethod
    def _runs_by_date(profile: str, monday: date) -> dict[str, list]:
        """Corridas realizadas na semana, por dia (arquivo local)."""

        sunday = monday + timedelta(days=6)

        activities = HomeSummaryBuilder._safe(
            lambda: ActivityArchiveRepository().load_activities(profile)
        ) or []

        out: dict[str, list] = {}

        for a in activities:

            day = a.start_date.date()

            if _is_run(a.sport) and monday <= day <= sunday:

                out.setdefault(day.isoformat(), []).append(a)

        return out

    @staticmethod
    def _executed(runs: list) -> dict:
        """O que o atleta CORREU no dia: km somados, pace médio e duração."""

        meters = sum(a.distance or 0 for a in runs)

        seconds = sum(a.moving_time or 0 for a in runs)

        km = round(meters / 1000, 2)

        pace = (
            PaceFormatter.format((seconds / 60) / km)
            if km > 0 and seconds > 0
            else None
        )

        return {
            "km": km,
            "pace": pace,
            "duration_min": round(seconds / 60),
            "runs": len(runs),
        }

    @staticmethod
    def _day(
        plan, i: int, day_en: str, monday: date, today: date, runs: dict,
        profile: str | None = None,
    ) -> dict:

        day_date = monday + timedelta(days=i)

        iso = day_date.isoformat()

        session = next((s for s in plan.sessions if s.day == day_en), None)

        done_runs = runs.get(iso) or []

        executed = WeekPlanBuilder._executed(done_runs) if done_runs else None

        if session is None:

            status = "done" if executed else "rest"

        elif executed:

            status = "done"

        elif day_date == today:

            status = "today"

        elif day_date < today:

            status = "missed"

        else:

            status = "upcoming"

        return {
            "day_en": day_en,
            "day_pt": _DAY_PT[day_en],
            "date_iso": iso,
            "date_num": day_date.day,
            "is_today": day_date == today,
            "is_past": day_date < today,
            "status": status,
            "session": WeekPlanBuilder._session(
                session, plan, profile, upcoming=day_date >= today
            ),
            "executed": executed,
        }

    @staticmethod
    def _detail(plan, s, profile: str | None = None) -> list[str]:
        """O DETALHE do treino, linha a linha, IGUAL ao que o coach manda no chat
        (um passo por linha — aquecimento, série principal, recuperação, desaquecimento
        —, a Dica e o Foco). Para QUALQUER sessão da semana (o chat só detalha as que
        ainda vão acontecer; o app mostra o plano inteiro). [] se não houver."""

        try:

            return WeeklyPlanMessageFormatter._execution_detail(
                s.workout_type, s, profile
            )

        except Exception:

            return []

    @staticmethod
    def _shoe(plan, s, profile: str | None, upcoming: bool) -> str:
        """A sugestão de tênis do coach (só pra treino que ainda vem; vazio sem
        armário cadastrado)."""

        if not upcoming:

            return ""

        try:

            return WeeklyPlanMessageFormatter._shoe_line(profile, plan, s) or ""

        except Exception:

            return ""

    @staticmethod
    def _session(
        s, plan=None, profile: str | None = None, upcoming: bool = False
    ) -> dict | None:

        if s is None:

            return None

        return {
            "workout_type": s.workout_type,
            "kind": _kind(s.workout_type),
            "objective": s.objective,
            "purpose": getattr(s, "purpose", "") or "",
            "structure": getattr(s, "structure", "") or "",
            "notes": getattr(s, "notes", "") or "",
            "distance_km": planned_km(s),
            # km ESTIMADO de uma sessão por tempo (duração ÷ pace) — entra no volume
            # planejado da semana; None quando a sessão é por distância
            "estimated_km": (
                s.effective_distance_km
                if planned_km(s) is None
                else None
            ),
            "duration_min": s.planned_duration_minutes,
            "pace_min": s.target_pace_min,
            "pace_max": s.target_pace_max,
            "adjusted": bool(getattr(s, "adjusted", False)),
            "adjustment_reason": getattr(s, "adjustment_reason", None),
            "is_oneoff": getattr(s, "origin", "plan") == "oneoff",
            "steps": [HomeSummaryBuilder._step(st) for st in (s.steps or [])],
            "detail": WeekPlanBuilder._detail(plan, s, profile),
            "shoe": WeekPlanBuilder._shoe(plan, s, profile, upcoming),
        }

    @staticmethod
    def _totals(days: list[dict]) -> dict:
        """Volume e treinos da semana: planejado × feito."""

        planned_km_total = 0.0

        sessions = 0

        done = 0

        done_km = 0.0

        for d in days:

            s = d["session"]

            if s is not None:

                sessions += 1

                planned_km_total += s["distance_km"] or s["estimated_km"] or 0

                if d["status"] == "done":

                    done += 1

            if d["executed"]:

                done_km += d["executed"]["km"]

        return {
            "planned_km": round(planned_km_total, 1),
            "done_km": round(done_km, 1),
            "sessions": sessions,
            "done_sessions": done,
        }
