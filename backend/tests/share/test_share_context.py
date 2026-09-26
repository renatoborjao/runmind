import asyncio
from datetime import date

from app.application.share import share_context
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.workout_analysis_repository import (
    WorkoutAnalysisRepository,
)

WEEK = date(2026, 9, 21)  # segunda


def _session(day, kind_text, km, pmin="6:15", pmax="6:25"):

    return PlannedSession(
        day=day, workout_type=kind_text, objective="",
        planned_distance_km=km, planned_duration_minutes=None,
        target_pace_min=pmin, target_pace_max=pmax,
    )


def _plan(week_start, *sessions):

    return TrainingPlan(
        athlete_name="Renato", objective="21k", phase="BUILD",
        weekly_volume=0.0, running_days=[s.day for s in sessions],
        week_start=week_start, sessions=list(sessions),
    )


def _item(date_iso, km):

    return {"date_iso": date_iso, "datetime": f"{date_iso}T07:00:00", "distance_km": km}


def _with_plans(monkeypatch, *plans):

    monkeypatch.setattr(share_context, "_plans", lambda profile: list(plans))


# ---- sessão do plano que a corrida cumpriu ---------------------------------


def test_planned_session_matches_same_day(monkeypatch):

    _with_plans(monkeypatch, _plan(
        WEEK,
        _session("Tuesday", "Limiar", 8.5, "5:25", "5:35"),
        _session("Saturday", "Longão Progressivo", 14.5),
    ))

    feed = [_item("2026-09-22", 8.4), _item("2026-09-26", 14.02)]

    got = share_context.planned_session("renato", feed, "2026-09-26", 14.02)

    assert got == {
        "workout_type": "Longão Progressivo", "distance_km": 14.5,
        "pace_min": "6:15", "pace_max": "6:25", "duration_min": None,
        "pace_label": "6:15–6:25", "pace_structured": False,
    }


def test_planned_session_matches_moved_day_by_distance(monkeypatch):
    """Longão de sábado corrido no domingo: casa pela distância."""

    _with_plans(monkeypatch, _plan(
        WEEK, _session("Saturday", "Longão Progressivo", 14.5),
    ))

    feed = [_item("2026-09-27", 14.1)]

    got = share_context.planned_session("renato", feed, "2026-09-27", 14.1)

    assert got is not None and got["workout_type"] == "Longão Progressivo"


def test_planned_session_extra_run_is_none(monkeypatch):
    """Corrida curta num dia sem sessão, longe de qualquer sessão = extra."""

    _with_plans(monkeypatch, _plan(
        WEEK, _session("Saturday", "Longão Progressivo", 14.5),
    ))

    feed = [_item("2026-09-23", 3.0)]

    assert share_context.planned_session("renato", feed, "2026-09-23", 3.0) is None


def test_planned_session_without_plan_that_week(monkeypatch):

    _with_plans(monkeypatch, _plan(
        date(2026, 9, 14), _session("Saturday", "Longão", 12.0),
    ))

    feed = [_item("2026-09-26", 12.0)]

    assert share_context.planned_session("renato", feed, "2026-09-26", 12.0) is None


# ---- meta de km do período ---------------------------------------------------


def test_period_goal_sums_sessions_inside_period(monkeypatch):

    _with_plans(
        monkeypatch,
        _plan(date(2026, 9, 14), _session("Saturday", "Longão", 12.0)),  # 19/09
        _plan(WEEK, _session("Tuesday", "Limiar", 8.5), _session("Saturday", "Longão", 14.5)),
        _plan(date(2026, 9, 28), _session("Thursday", "Rodagem", 6.0)),  # 01/10
    )

    week = share_context.period_goal_km("renato", WEEK, date(2026, 9, 27))
    month = share_context.period_goal_km("renato", date(2026, 9, 1), date(2026, 9, 30))

    assert week == 23.0
    assert month == 35.0  # 01/10 fica fora de setembro


def test_period_goal_uses_weekly_volume_with_time_based_sessions(monkeypatch):
    """Semana com sessões por TEMPO (sem km): a meta é o weekly_volume do plano,
    não só a soma das sessões com distância (caso real renato2: 14,5 vs 27,5)."""

    plan = _plan(
        WEEK,
        _session("Tuesday", "Fartlek", None),
        _session("Thursday", "Rodagem Leve", None),
        _session("Saturday", "Longão Progressivo", 14.5),
    )
    plan.sessions[0].planned_duration_minutes = 50
    plan.sessions[1].planned_duration_minutes = 45
    plan.weekly_volume = 27.5

    _with_plans(monkeypatch, plan)

    assert share_context.period_goal_km("renato", WEEK, date(2026, 9, 27)) == 27.5

    # recorte: só terça+quinta (proporcional ao km estimado de cada sessão)
    part = share_context.period_goal_km("renato", WEEK, date(2026, 9, 24))
    assert part == 14.4  # (50+45 min ÷ 6) de 30,3 km-peso × 27,5


def test_period_goal_none_without_plan(monkeypatch):

    _with_plans(monkeypatch)

    assert share_context.period_goal_km("renato", WEEK, date(2026, 9, 27)) is None


# ---- frase do coach ----------------------------------------------------------


ANALYSIS = (
    "🏃 Ritmind\n\n📊 Análise\n• Renato, você fechou os últimos 4 km abaixo de "
    "5:45 num progressivo muito bem dosado. Continue assim.\n• Outra coisa."
)


def _repo_with_analysis(tmp_path, monkeypatch):

    monkeypatch.setattr(
        "app.infrastructure.persistence.workout_analysis_repository._STORAGE", tmp_path,
    )

    repo = WorkoutAnalysisRepository()

    repo.record("renato", 1, "2026-09-26", 14.02, ANALYSIS, "LONG_RUN")

    return repo


def test_coach_quote_generates_once_and_caches(tmp_path, monkeypatch):

    repo = _repo_with_analysis(tmp_path, monkeypatch)

    calls = []

    async def fake_generate(**kwargs):

        calls.append(kwargs)

        return '"Progressivo de livro: fechou abaixo de 5:45."\n'

    monkeypatch.setattr(share_context, "generate_text", fake_generate)

    q1 = asyncio.run(share_context.coach_quote("renato", "2026-09-26", 14.0))
    q2 = asyncio.run(share_context.coach_quote("renato", "2026-09-26", 14.0))

    assert q1 == q2 == "Progressivo de livro: fechou abaixo de 5:45."
    assert len(calls) == 1  # 2ª vez veio do cache na análise
    assert repo.find("renato", "2026-09-26", 14.0)["share_quote"] == q1


def test_coach_quote_falls_back_without_ai_and_does_not_cache(tmp_path, monkeypatch):

    repo = _repo_with_analysis(tmp_path, monkeypatch)

    async def broken(**kwargs):

        raise RuntimeError("gemini fora")

    monkeypatch.setattr(share_context, "generate_text", broken)

    q = asyncio.run(share_context.coach_quote("renato", "2026-09-26", 14.0))

    assert q == "Você fechou os últimos 4 km abaixo de 5:45 num progressivo muito bem dosado."
    assert "share_quote" not in repo.find("renato", "2026-09-26", 14.0)


def test_coach_quote_none_without_analysis(tmp_path, monkeypatch):

    monkeypatch.setattr(
        "app.infrastructure.persistence.workout_analysis_repository._STORAGE", tmp_path,
    )

    assert asyncio.run(share_context.coach_quote("renato", "2026-09-26", 14.0)) is None


def test_clean_quote_trims_long_text():

    long = "palavra " * 40

    q = share_context._clean_quote(long)

    assert len(q) <= share_context.QUOTE_MAX_CHARS + 1 and q.endswith("…")


# ---- ritmo do plano vindo dos PASSOS (target_pace_* vazio) ------------------

from app.domain.entities.workout_step import WorkoutStep  # noqa: E402


def _stepped(kind_text, steps):

    s = _session("Saturday", kind_text, 14.5, None, None)
    s.steps = steps
    return s


def test_pace_continuous_from_steps_is_comparable():

    got = share_context._planned_pace(_stepped("Rodagem Leve", [
        WorkoutStep(kind="run", duration_sec=2700, pace_min="6:20", pace_max="6:45"),
    ]))

    assert got == {"pace_min": "6:20", "pace_max": "6:45", "pace_label": "6:20–6:45", "pace_structured": False}


def test_pace_progressive_is_structured_label():

    got = share_context._planned_pace(_stepped("Longão Progressivo", [
        WorkoutStep(kind="run", distance_m=10000, pace_min="6:20", pace_max="6:45"),
        WorkoutStep(kind="interval", distance_m=4000, pace_min="5:25", pace_max="5:40"),
        WorkoutStep(kind="cooldown", distance_m=500, pace_min="6:50", pace_max="7:30"),
    ]))

    assert got["pace_structured"] is True and got["pace_min"] is None
    assert got["pace_label"] == "6:20–6:45 → 5:25–5:40"


def test_pace_intervals_show_the_reps_pace():
    """Fartlek: ritmo do tiro, sem aquecimento/trote; e sem comparar média."""

    got = share_context._planned_pace(_stepped("Fartlek", [
        WorkoutStep(kind="warmup", duration_sec=600),
        WorkoutStep(kind="repeat", reps=8, steps=[
            WorkoutStep(kind="interval", duration_sec=120, pace_min="4:50", pace_max="5:05"),
            WorkoutStep(kind="recovery", duration_sec=90),
        ]),
        WorkoutStep(kind="cooldown", duration_sec=720),
    ]))

    assert got == {"pace_min": None, "pace_max": None, "pace_label": "4:50–5:05 (tiros)", "pace_structured": True}


def test_pace_repeated_km_blocks_same_pace_is_continuous():
    """Rodagem dividida em 8x1 km no mesmo ritmo (bipe por km) = contínua."""

    got = share_context._planned_pace(_stepped("Rodagem", [
        WorkoutStep(kind="repeat", reps=8, steps=[
            WorkoutStep(kind="run", distance_m=1000, pace_min="6:30", pace_max="7:10"),
        ]),
        WorkoutStep(kind="run", distance_m=500, pace_min="6:30", pace_max="7:10"),
    ]))

    assert got["pace_structured"] is False and got["pace_label"] == "6:30–7:10"


def test_pace_nowhere_is_free():

    got = share_context._planned_pace(_stepped("Rodagem", []))

    assert got["pace_label"] is None and got["pace_structured"] is False
