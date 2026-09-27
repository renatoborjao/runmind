from datetime import date
from types import SimpleNamespace

from app.application.coach.planning.plan_guard import PlanGuard
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import parse_steps

# renato2 real: limiar 5:29, VO2 5:04
METRICS = SimpleNamespace(threshold_pace=5 + 29 / 60, vo2_pace=5 + 4 / 60)


def _session(day, wtype, steps=None):
    s = PlannedSession(day, wtype, "", 8.0, None, None, None)
    s.steps = parse_steps(steps or [])
    return s


def _plan(sessions):
    return TrainingPlan(
        athlete_name="R", objective="15k", phase="BUILD", weekly_volume=30,
        running_days=[s.day for s in sessions], week_start=date(2026, 9, 28),
        sessions=sessions,
    )


def test_three_runs_with_two_hard_sessions_violates_budget():
    """Semana real do renato2: Fartlek + Longão Progressivo em 3 corridas."""

    plan = _plan([
        _session("Tuesday", "Fartlek"),
        _session("Friday", "Rodagem Leve"),
        _session("Saturday", "Longão Progressivo"),
    ])

    issues = PlanGuard.violations(plan, None)

    assert len(issues) == 1 and "2 sessões FORTES" in issues[0]


def test_one_quality_plus_constant_long_is_fine():

    plan = _plan([
        _session("Tuesday", "Intervalado de Limiar"),
        _session("Friday", "Rodagem Leve"),
        _session("Saturday", "Longão"),
    ])

    assert PlanGuard.violations(plan, None) == []


def test_four_runs_allow_two_quality_sessions():

    plan = _plan([
        _session("Monday", "Rodagem Leve"),
        _session("Tuesday", "Fartlek"),
        _session("Thursday", "Tempo Run"),
        _session("Saturday", "Longão"),
    ])

    assert PlanGuard.violations(plan, None) == []


def test_sustained_block_faster_than_threshold_is_flagged():
    """'Longão Misto' com bloco de 3 km a 5:05 com o limiar em 5:29."""

    plan = _plan([
        _session("Saturday", "Longão", [
            {"kind": "run", "distance_km": 10, "pace_min": "6:20", "pace_max": "6:40"},
            {"kind": "run", "distance_km": 3, "pace_min": "5:05", "pace_max": "5:15"},
        ]),
    ])

    issues = PlanGuard.violations(plan, METRICS)

    assert any("LIMIAR ATUAL" in i and "5:29" in i for i in issues)


def test_reps_faster_than_vo2_flagged_but_strides_allowed():

    reps = _plan([_session("Tuesday", "Intervalado", [
        {"kind": "repeat", "reps": 6, "steps": [
            {"kind": "interval", "distance_m": 800, "pace_min": "4:40", "pace_max": "4:50"},
            {"kind": "recovery", "duration_min": 2},
        ]},
    ])])

    assert any("VO2 ATUAL" in i for i in PlanGuard.violations(reps, METRICS))

    strides = _plan([_session("Friday", "Rodagem com acelerações", [
        {"kind": "run", "distance_km": 6, "pace_min": "6:20", "pace_max": "6:40"},
        {"kind": "repeat", "reps": 6, "steps": [
            {"kind": "interval", "distance_m": 100, "pace_min": "4:10", "pace_max": "4:30"},
            {"kind": "recovery", "duration_min": 1},
        ]},
    ])])

    assert PlanGuard.violations(strides, METRICS) == []


def test_correction_block_lists_every_issue():

    block = PlanGuard.correction_block(["a", "b"])

    assert "CORREÇÕES OBRIGATÓRIAS" in block and "- a" in block and "- b" in block


EASY = SimpleNamespace(
    threshold_pace=5.7, vo2_pace=5.2, easy_pace_min=6.4, easy_pace_max=6.8,
)


def test_plan_far_below_real_volume_is_flagged():
    """Fernanda real: corre ~22 km/sem, recebia ~14 km (e sem o longão)."""

    plan = _plan([
        _session("Tuesday", "Rodagem Leve"),
        _session("Friday", "Rodagem com Acelerações"),
        _session("Sunday", "Rodagem de Consolidação"),
    ])
    for s, km in zip(plan.sessions, (4.5, 4.5, 5.5)):
        s.planned_distance_km = km

    issues = PlanGuard.violations(plan, EASY, real_weekly_km=21.7)

    assert any("bem abaixo do que ele corre" in i for i in issues)

    # com motivo real (sobrecarga/polimento), cortar é permitido
    assert not any(
        "bem abaixo" in i
        for i in PlanGuard.violations(plan, EASY, 21.7, allow_reduction=True)
    )


def test_big_jump_over_real_volume_is_flagged():

    plan = _plan([_session("Tuesday", "Rodagem Leve"), _session("Sunday", "Longão")])
    plan.sessions[0].planned_distance_km = 10
    plan.sessions[1].planned_distance_km = 20

    issues = PlanGuard.violations(plan, EASY, real_weekly_km=20)

    assert any("salto de 50%" in i for i in issues)


def test_time_based_sessions_count_toward_volume():

    plan = _plan([_session("Tuesday", "Rodagem Leve")])
    plan.sessions[0].planned_distance_km = None
    plan.sessions[0].planned_duration_minutes = 66  # ~10 km a 6:36

    assert round(PlanGuard.planned_km(plan.sessions, EASY)) == 10


def test_green_body_lets_the_ai_use_two_hard_sessions_in_three_runs():
    """Teto fixo só protege quando o corpo pede; corpo verde → a IA decide."""

    plan = _plan([
        _session("Tuesday", "Fartlek"),
        _session("Friday", "Rodagem Leve"),
        _session("Saturday", "Longão Progressivo"),
    ])

    assert PlanGuard.violations(plan, None, body_green=True) == []
    assert PlanGuard.violations(plan, None, body_green=False) != []
