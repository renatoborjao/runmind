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


# ---- executado fase a fase (voltas do relógio × passos) ---------------------

from app.domain.entities.block_comparison import ExecutedBlock  # noqa: E402


def _blk(kind, pmin, pmax, pace_min_km, dist=None, dur=None, ok=True, label=""):

    exec_dist = dist or (dur / 60 / pace_min_km * 1000 if dur else 0)
    exec_dur = exec_dist / 1000 * pace_min_km * 60

    return ExecutedBlock(
        kind=kind, label=label, planned_distance_m=dist, planned_duration_sec=dur,
        pace_min=pmin, pace_max=pmax, executed_distance_m=exec_dist,
        executed_duration_sec=exec_dur, executed_pace=pace_min_km, executed_hr=None,
        within_target=ok,
    )


def test_build_phases_fartlek_is_one_series_of_reps():
    """Fartlek real do renato2: 8×2min, aquecimento/trote/desaquecimento fora."""

    paces = [4.64, 4.92, 4.77, 5.06, 5.05, 5.0, 4.87, 4.98]
    blocks = [_blk("warmup", None, None, 6.49, dur=600)]
    for i, pc in enumerate(paces):
        blocks.append(_blk("interval", "4:50", "5:05", pc, dur=120, ok=(i != 0)))
        blocks.append(_blk("recovery", None, None, 6.5, dur=90))
    blocks.append(_blk("cooldown", None, None, 7.0, dur=720))

    phases = share_context.build_phases(blocks)

    assert len(phases) == 1
    ph = phases[0]
    assert ph["kind"] == "tiros" and ph["label"] == "8× 2min"
    assert ph["target"] == "4:50–5:05" and (ph["target_min_sec"], ph["target_max_sec"]) == (290, 305)
    assert ph["ok"] == 7 and ph["total"] == 8
    assert ph["reps"][0] == {"pace_sec": 278, "ok": False}


def test_build_phases_progressive_long_run_is_blocks():
    """Longão real: 10 km leve + 4 km forte (1 tiro só = bloco, não série)."""

    phases = share_context.build_phases([
        _blk("run", "6:20", "6:45", 6.35, dist=10000),
        _blk("interval", "5:25", "5:40", 5.96, dist=4000, ok=False),
        _blk("cooldown", "6:50", "7:30", 7.0, dist=500),
    ])

    assert [(p["kind"], p["label"], p["target"], p["ok"], p["total"]) for p in phases] == [
        ("bloco", "10 km", "6:20–6:45", 1, 1),
        ("bloco", "4 km", "5:25–5:40", 0, 1),
    ]
    assert phases[0]["avg_pace_sec"] == 381


def test_build_phases_km_splits_group_by_target():
    """Longão do Maurício no relógio como 9×1 km + 3×1 km: 2 blocos."""

    blocks = [_blk("run", "6:10", "6:40", 6.3, dist=1000) for _ in range(9)]
    blocks += [_blk("run", "5:40", "6:00", pc, dist=1000, ok=ok) for pc, ok in [(6.53, False), (5.67, True), (5.6, True)]]

    phases = share_context.build_phases(blocks)

    assert [(p["label"], p["ok"], p["total"]) for p in phases] == [("9 km", 9, 9), ("3 km", 2, 3)]


def test_build_phases_none_without_paced_blocks():

    assert share_context.build_phases([_blk("run", None, None, 6.0, dist=8000)]) is None


def _session_with_steps():

    s = _session("Tuesday", "Fartlek", None, None, None)
    s.steps = [WorkoutStep(kind="interval", duration_sec=120, pace_min="4:50", pace_max="5:05")]
    return s


def _isolate_phase_cache(tmp_path, monkeypatch):

    monkeypatch.setattr("app.infrastructure.persistence.share_phases_store._STORAGE", tmp_path)
    monkeypatch.setattr(share_context.GarminClient, "is_connected", staticmethod(lambda p: True))


def test_execution_phases_fetches_once_then_caches(tmp_path, monkeypatch):

    _isolate_phase_cache(tmp_path, monkeypatch)
    calls = []

    def fake(profile, date_iso, km, session):

        calls.append(date_iso)
        return [{"kind": "tiros", "label": "8× 2min"}]

    monkeypatch.setattr(share_context, "_garmin_phases", fake)

    s = _session_with_steps()
    a = asyncio.run(share_context.execution_phases("renato", "2026-09-22", 8.32, s))
    b = asyncio.run(share_context.execution_phases("renato", "2026-09-22", 8.32, s))

    assert a == b == [{"kind": "tiros", "label": "8× 2min"}]
    assert len(calls) == 1


def test_execution_phases_caches_no_match_but_not_errors(tmp_path, monkeypatch):

    _isolate_phase_cache(tmp_path, monkeypatch)
    calls = []

    def boom(*args):

        calls.append(1)
        raise RuntimeError("garmin fora")

    monkeypatch.setattr(share_context, "_garmin_phases", boom)
    s = _session_with_steps()

    assert asyncio.run(share_context.execution_phases("renato", "2026-09-22", 8.3, s)) is None
    assert asyncio.run(share_context.execution_phases("renato", "2026-09-22", 8.3, s)) is None
    assert len(calls) == 2  # erro não fica em cache: tenta de novo

    monkeypatch.setattr(share_context, "_garmin_phases", lambda *a: calls.append(2))
    asyncio.run(share_context.execution_phases("renato", "2026-09-23", 5.0, s))
    asyncio.run(share_context.execution_phases("renato", "2026-09-23", 5.0, s))
    assert calls.count(2) == 1  # "não pareou" (None) fica em cache


def test_execution_phases_skips_without_garmin(tmp_path, monkeypatch):

    monkeypatch.setattr("app.infrastructure.persistence.share_phases_store._STORAGE", tmp_path)
    monkeypatch.setattr(share_context.GarminClient, "is_connected", staticmethod(lambda p: False))
    monkeypatch.setattr(share_context, "_garmin_phases", lambda *a: (_ for _ in ()).throw(AssertionError("não devia chamar")))

    assert asyncio.run(share_context.execution_phases("renato", "2026-09-22", 8.3, _session_with_steps())) is None
