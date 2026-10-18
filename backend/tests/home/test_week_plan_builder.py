"""O plano da semana da tela Treino: o do chat, navegável — com o feito ao lado de cada
dia e o histórico de semanas. Caso real: renato2 (semana 12–18/10, retorno da gripe)."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.home.week_plan_builder import WeekPlanBuilder
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import COOLDOWN, RUN, WARMUP, WorkoutStep

WMOD = "app.application.home.week_plan_builder"
HMOD = "app.application.home.home_summary_builder"

MONDAY = date(2026, 10, 12)
PREV_MONDAY = date(2026, 10, 5)

# quinta-feira 15/10, 09:00 — a semana está no meio
THU = datetime(2026, 10, 15, 9, 0, 0)


def _session(day, kind="Rodagem Leve", km=6.0, steps=None, **extra):

    return PlannedSession(
        day=day, workout_type=kind, objective="Base aeróbica",
        planned_distance_km=km, planned_duration_minutes=None,
        target_pace_min="6:20", target_pace_max="6:40",
        steps=steps or [], **extra,
    )


def _plan(week_start, sessions, **extra):

    return TrainingPlan(
        athlete_name="Renato", objective="meia", phase="BUILD",
        weekly_volume=30.0, running_days=[s.day for s in sessions],
        week_start=week_start, sessions=sessions, source="runmind", **extra,
    )


def _run(day, km, minutes):

    return SimpleNamespace(
        sport="Run", start_date=datetime(day.year, day.month, day.day, 6, 30),
        distance=km * 1000.0, moving_time=minutes * 60, id=1, name="Corrida",
    )


def _build(current, history=(), activities=(), week_start=None, now=THU, race=None):

    repo = SimpleNamespace(load=lambda p: current, history=lambda p: list(history))

    runner = SimpleNamespace(
        target_race=race[0] if race else None,
        race_date=race[1] if race else None,
        target_time=race[2] if race else None,
    )

    archive = SimpleNamespace(load_activities=lambda p: list(activities))

    with (
        patch(f"{WMOD}.now_local", return_value=now),
        patch(f"{WMOD}.WeeklyPlanRepository", lambda: repo),
        patch(f"{HMOD}.WeeklyPlanRepository", lambda: repo),
        patch(f"{WMOD}.ActivityArchiveRepository", lambda: archive),
        patch(
            "app.application.home.workouts_builder.RunnerProfileRepository",
            lambda: SimpleNamespace(load=lambda p: runner),
        ),
    ):

        return WeekPlanBuilder.build("renato2", week_start)


def _longao_steps():

    return [
        WorkoutStep(kind=WARMUP, distance_m=2000, pace_min="6:30", pace_max="6:45"),
        WorkoutStep(kind=RUN, distance_m=10000, pace_min="6:20", pace_max="6:35"),
        WorkoutStep(kind=COOLDOWN),
    ]


def test_week_carries_the_coach_header_like_the_chat_message():

    plan = _plan(
        MONDAY, [_session("Tuesday")],
        weekly_objective="Retomar o volume com calma depois da gripe",
        block_label="semana 2 de 4 — construir resistência",
        extra_day_note="Percebi um treino a mais na sexta; quer oficializar?",
    )

    out = _build(plan)

    assert out["has_plan"] and out["is_current"]
    assert out["week_start"] == "2026-10-12" and out["week_end"] == "2026-10-18"
    assert out["objective"].startswith("Retomar o volume")
    assert out["block_label"].startswith("semana 2 de 4")
    assert out["phase"] == "BUILD" and out["phase_label"] == "Construção"
    assert out["extra_day_note"].startswith("Percebi um treino")
    assert len(out["days"]) == 7
    assert [d["day_pt"] for d in out["days"]][:2] == ["Seg", "Ter"]


def test_status_per_day_done_today_upcoming_missed_and_rest():

    plan = _plan(
        MONDAY,
        [
            _session("Monday"),       # passou, sem corrida -> missed
            _session("Tuesday"),      # passou, com corrida -> done
            _session("Thursday"),     # hoje, sem corrida -> today
            _session("Saturday"),     # à frente -> upcoming
        ],
    )

    out = _build(plan, activities=[_run(date(2026, 10, 13), 6.1, 38)])

    status = {d["day_en"]: d["status"] for d in out["days"]}

    assert status == {
        "Monday": "missed", "Tuesday": "done", "Wednesday": "rest",
        "Thursday": "today", "Friday": "rest", "Saturday": "upcoming", "Sunday": "rest",
    }


def test_executed_km_pace_and_totals_sit_next_to_the_plan():

    plan = _plan(MONDAY, [_session("Tuesday", km=6.0), _session("Saturday", km=12.0)])

    out = _build(plan, activities=[_run(date(2026, 10, 13), 6.1, 38)])

    tue = next(d for d in out["days"] if d["day_en"] == "Tuesday")

    assert tue["executed"] == {"km": 6.1, "pace": "6:14", "duration_min": 38, "runs": 1}
    assert out["totals"] == {
        "planned_km": 18.0, "done_km": 6.1, "sessions": 2, "done_sessions": 1,
    }


def test_run_on_a_rest_day_still_counts_as_done_volume():
    """Correu num dia sem treino planejado: aparece como feito e soma no volume."""

    out = _build(
        _plan(MONDAY, [_session("Tuesday")]),
        activities=[_run(date(2026, 10, 14), 5.0, 31)],
    )

    wed = next(d for d in out["days"] if d["day_en"] == "Wednesday")

    assert wed["status"] == "done" and wed["session"] is None
    assert out["totals"]["done_km"] == 5.0


def test_session_carries_steps_and_the_free_cooldown_is_open():

    plan = _plan(
        MONDAY, [_session("Saturday", kind="Longão", km=12.0, steps=_longao_steps(),
                          purpose="resistência aeróbica", structure="2 + 10 + livre")],
    )

    sat = next(d for d in _build(plan)["days"] if d["day_en"] == "Saturday")

    s = sat["session"]

    assert s["workout_type"] == "Longão" and s["kind"] == "long"
    assert s["purpose"] == "resistência aeróbica" and s["structure"] == "2 + 10 + livre"
    assert [st["kind"] for st in s["steps"]] == ["warmup", "run", "cooldown"]
    assert s["steps"][2]["distance_m"] is None            # desaquecimento livre
    assert s["distance_km"] == 12.0                        # warmup + contínuo (soma dos passos)


def test_previous_weeks_come_from_history_and_navigation_links_exist():

    prev = _plan(PREV_MONDAY, [_session("Tuesday")], weekly_objective="semana passada")

    current = _plan(MONDAY, [_session("Tuesday")], weekly_objective="esta semana")

    now_view = _build(current, history=[prev])

    assert now_view["prev_week_start"] == "2026-10-05" and now_view["next_week_start"] is None

    old = _build(current, history=[prev], week_start="2026-10-05")

    assert old["objective"] == "semana passada" and old["is_current"] is False
    assert old["prev_week_start"] is None and old["next_week_start"] == "2026-10-12"

    # o dia de uma semana passada sem corrida é "não realizado", nunca "hoje"
    assert all(d["status"] != "today" for d in old["days"])


def test_unknown_week_or_no_plan_is_a_clean_empty_answer():

    assert _build(None)["has_plan"] is False

    plan = _plan(MONDAY, [_session("Tuesday")])

    out = _build(plan, week_start="2026-01-05")

    assert out["has_plan"] is False


def test_deload_and_oneoff_flags_travel_to_the_screen():

    plan = _plan(
        MONDAY, [_session("Tuesday", origin="oneoff", adjusted=True,
                          adjustment_reason="gripe")],
    )

    with patch.object(TrainingPlan, "is_deload", new=True, create=True):

        out = _build(plan)

    tue = next(d for d in out["days"] if d["day_en"] == "Tuesday")["session"]

    assert tue["is_oneoff"] is True and tue["adjusted"] is True
    assert tue["adjustment_reason"] == "gripe"


def test_the_race_countdown_travels_with_the_week():

    out = _build(
        _plan(MONDAY, [_session("Tuesday")]),
        race=("Villa-Lobos (15 km)", "2026-12-20", "1:15:00"),
    )

    assert out["race"] == {
        "name": "Villa-Lobos (15 km)", "date_iso": "2026-12-20",
        "target_time": "1:15:00", "days_until": 66,
    }

    assert _build(_plan(MONDAY, [_session("Tuesday")]))["race"] is None


def test_time_based_session_counts_its_estimated_km_in_the_planned_volume():
    """'Retorno de pausa/lesão' é por tempo (sem km): o volume planejado conta o km
    ESTIMADO (duração ÷ pace), pra não aparecer '21 de 12 km' (caso real do renato2)."""

    by_time = PlannedSession(
        day="Monday", workout_type="Retorno de pausa/lesão", objective="voltar",
        planned_distance_km=None, planned_duration_minutes=45,
        target_pace_min="6:30", target_pace_max="7:00", estimated_distance_km=6.5,
    )

    out = _build(_plan(MONDAY, [by_time, _session("Saturday", km=12.0)]))

    mon = next(d for d in out["days"] if d["day_en"] == "Monday")["session"]

    assert mon["distance_km"] is None and mon["estimated_km"] == 6.5
    assert out["totals"]["planned_km"] == 18.5


# ---- o DETALHE do chat, linha a linha, pra TODA sessão da semana ---------------

_STRUCTURE = (
    "Aquecimento: 2 km de rodagem leve (6:20 a 6:50/km).\n"
    "Série Principal: 3x 1.5 km no ritmo-alvo (5:30 a 5:45/km).\n"
    "Desaquecimento: 1 km soltando as pernas."
)


def test_detail_lines_are_the_same_the_chat_sends_one_step_per_line():

    plan = _plan(
        MONDAY,
        [_session("Tuesday", kind="Limiar Intervalado", km=9.0,
                  structure=_STRUCTURE, purpose="sentir o esforço do ritmo-alvo")],
    )

    sess = next(d for d in _build(plan)["days"] if d["day_en"] == "Tuesday")["session"]

    assert sess["detail"][0] == "Aquecimento: 2 km de rodagem leve (6:20 a 6:50/km)."
    assert any(line.startswith("Série Principal") for line in sess["detail"])
    # o foco da sessão entra (como no chat) quando a prosa não o trouxe
    assert sess["detail"][-1] == "Foco: sentir o esforço do ritmo-alvo"


def test_detail_is_there_even_for_sessions_already_done():
    """O chat só detalha o que ainda vem; o app mostra o plano INTEIRO da semana."""

    plan = _plan(MONDAY, [_session("Tuesday", structure=_STRUCTURE)])

    out = _build(plan, activities=[_run(date(2026, 10, 13), 6.1, 38)])

    tue = next(d for d in out["days"] if d["day_en"] == "Tuesday")

    assert tue["status"] == "done" and len(tue["session"]["detail"]) >= 3


def test_shoe_suggestion_only_for_what_is_still_to_come():

    plan = _plan(
        MONDAY,
        [
            _session("Tuesday", structure=_STRUCTURE),
            _session("Saturday", structure=_STRUCTURE),
        ],
    )

    with patch.object(
        WeeklyPlanMessageFormatter, "_shoe_line", return_value="👟 Novablast — rodagem leve"
    ):

        out = _build(plan)

    by_day = {d["day_en"]: d["session"] for d in out["days"] if d["session"]}

    assert by_day["Tuesday"]["shoe"] == ""                       # já passou
    assert by_day["Saturday"]["shoe"] == "👟 Novablast — rodagem leve"


def test_detail_failure_never_breaks_the_week():

    plan = _plan(MONDAY, [_session("Tuesday")])

    with patch.object(
        WeeklyPlanMessageFormatter, "_execution_detail", side_effect=RuntimeError("x")
    ):

        out = _build(plan)

    assert next(d for d in out["days"] if d["day_en"] == "Tuesday")["session"]["detail"] == []
