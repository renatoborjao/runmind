"""PLANEJADO × EXECUTADO vivo (Renato 28/09: "o coach precisa, com a base dos
treinos, ver o planejado × executado e saber o que propor; ter a visão se o
atleta está evoluindo"). Só fatos por sessão — a calibração é da IA."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.application.coach.planning.workout_menu import STEPS_RULE
from app.application.history.execution_log import (
    ExecutionLog,
    entry_from_comparison,
)
from app.domain.entities.block_comparison import BlockComparison, ExecutedBlock
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import WorkoutStep, parse_steps
from tests.coach.factories import make_activity

WEEK = date(2026, 9, 21)
TODAY = date(2026, 9, 28)


def _session(day, kind, km=None, mins=None, fast=None, slow=None, steps=None):
    s = PlannedSession(day, kind, "", km, mins, fast, slow)
    s.steps = steps or []
    return s


def _plan(*sessions):
    return TrainingPlan(
        athlete_name="R", objective="15k", phase="BUILD", weekly_volume=30,
        running_days=[s.day for s in sessions], week_start=WEEK,
        sessions=list(sessions),
    )


def _run(day: int, km: float, pace_sec: int, hr: int, act_id: int):
    return make_activity(
        id=act_id,
        start_date=datetime(2026, 9, day, 9, tzinfo=timezone.utc),
        distance=km * 1000, moving_time=int(km * pace_sec),
        average_speed=1000 / pace_sec, average_heartrate=hr,
    )


def _block(kind, m, pace_min_km, hr, fast=None, slow=None, ok=None):
    return ExecutedBlock(
        kind=kind, label=kind, planned_distance_m=m, planned_duration_sec=None,
        pace_min=fast, pace_max=slow, executed_distance_m=m,
        executed_duration_sec=m * pace_min_km * 60 / 1000,
        executed_pace=pace_min_km, executed_hr=hr, within_target=ok,
    )


INTERVAL_STEPS = [
    WorkoutStep(kind="warmup", distance_m=2000),
    WorkoutStep(kind="repeat", reps=8, steps=[
        WorkoutStep(kind="interval", distance_m=200, pace_min="3:45", pace_max="3:55"),
        WorkoutStep(kind="recovery", distance_m=200),
    ]),
]


def test_entry_keeps_only_the_stimulus_blocks_and_what_was_left_undone():

    comparison = BlockComparison(
        blocks=[
            _block("warmup", 2000, 6.8, 140),
            _block("interval", 200, 3 + 41 / 60, 165, "3:45", "3:55", False),
            _block("recovery", 200, 8.0, 150),
        ],
        missing=["Desaquecimento"],
    )

    entry = entry_from_comparison(comparison)

    assert [b["kind"] for b in entry["blocks"]] == ["interval"]
    assert entry["blocks"][0] == {
        "kind": "interval", "m": 200, "pace": "3:41", "hr": 165,
        "target": "3:45-3:55", "ok": False,
    }
    assert entry["missing"] == ["Desaquecimento"]
    assert entry_from_comparison(None) is None


def test_intervals_show_how_many_hit_the_range_and_the_spread():

    plan = _plan(_session("Tuesday", "Intervalado Curto", km=7.2, steps=INTERVAL_STEPS))
    blocks = [
        {"kind": "interval", "m": 200, "pace": p, "hr": 165, "target": "3:45-3:55", "ok": ok}
        for p, ok in [("3:41", False)] + [("3:50", True)] * 6 + [("3:58", False)]
    ]
    log = {99: {"date": "2026-09-22", "km": 7.3, "blocks": blocks, "missing": []}}

    text = ExecutionLog.render([plan], [_run(22, 7.3, 370, 150, 99)], log, [], TODAY)

    assert "PLANEJADO × EXECUTADO" in text
    assert "ter 22/09 · Intervalado Curto (7.2 km) → 7.3 km a 6:10, FC 150" in text
    assert "tiros 8× 200 m (alvo 3:45-3:55): 6 de 8 no alvo, 3:41 a 3:58, FC ~165" in text


def test_continuous_run_is_measured_against_the_range():

    plan = _plan(
        _session("Friday", "Rodagem Leve", mins=45, fast="6:20", slow="6:45"),
        _session("Saturday", "Longão", km=14.0, fast="6:20", slow="6:45"),
    )

    text = ExecutionLog.render(
        [plan], [_run(25, 8.5, 383, 144, 1), _run(26, 14.0, 417, 150, 2)], {}, [], TODAY,
    )

    assert "sex 25/09 · Rodagem Leve (45 min; alvo 6:20-6:45) → 8.5 km em 54 min a 6:23, FC 144 (na faixa)" in text
    # longão sem passos (plano antigo): o alvo da sessão pode ser envelope —
    # mostra, mas não julga a média
    assert text.endswith("sáb 26/09 · Longão (14 km; alvo 6:20-6:45) → 14.0 km a 6:57, FC 150")


def test_single_pace_in_the_steps_is_the_target_to_compare():

    steps = [WorkoutStep(kind="run", distance_m=12000, pace_min="6:20", pace_max="6:45")]
    plan = _plan(_session("Saturday", "Longão Aeróbico", km=12.0, steps=steps))

    text = ExecutionLog.render([plan], [_run(26, 12.0, 417, 150, 1)], {}, [], TODAY)

    assert "Longão Aeróbico (12 km; alvo 6:20-6:45) → 12.0 km a 6:57, FC 150 (12s/km mais lento)" in text


def test_mixed_session_envelope_is_not_used_as_a_target():
    """Longão misto com alvo de sessão 5:05-6:40 (envelope do aquecimento ao
    bloco forte): a média "na faixa" não diz nada."""

    steps = [
        WorkoutStep(kind="run", distance_m=10000, pace_min="6:15", pace_max="6:40"),
        WorkoutStep(kind="run", distance_m=4000, pace_min="5:05", pace_max="5:15"),
    ]
    plan = _plan(_session("Saturday", "Longão Misto", km=15.0, fast="5:05", slow="6:40", steps=steps))

    text = ExecutionLog.render([plan], [_run(26, 14.0, 372, 160, 1)], {}, [], TODAY)
    line = text.splitlines()[-1]

    assert line == "- sáb 26/09 · Longão Misto (15 km) → 14.0 km a 6:12, FC 160"


def test_blocks_from_the_other_source_match_by_day_and_distance():
    """A mesma corrida vem com id do Garmin e do Strava — casa por dia + km."""

    plan = _plan(_session("Saturday", "Longão Progressivo", km=14.5))
    log = {555: {"date": "2026-09-26", "km": 13.42, "missing": ["Desaquecimento"], "blocks": [
        {"kind": "run", "m": 10000, "pace": "6:21", "hr": 156, "target": "6:20-6:45", "ok": True},
        {"kind": "interval", "m": 3424, "pace": "5:57", "hr": 166, "target": "5:25-5:40", "ok": False},
    ]}}

    text = ExecutionLog.render([plan], [_run(26, 13.4, 375, 159, 1)], log, [], TODAY)

    assert (
        "blocos: contínuo 10.0 km a 6:21 (alvo 6:20-6:45: na faixa), FC 156 | "
        "tiro 3.4 km a 5:57 (alvo 5:25-5:40: 17s/km mais lento), FC 166 | "
        "não fez: Desaquecimento"
    ) in text


def test_missed_session_is_shown_but_todays_still_pending_is_not():

    plan = _plan(_session("Thursday", "Rodagem", km=8.0), _session("Sunday", "Regenerativo", km=5.0))

    text = ExecutionLog.render([plan], [], {}, [], date(2026, 9, 27))

    assert "qui 24/09 · Rodagem (8 km) → NÃO FEZ" in text
    assert "Regenerativo" not in text


def test_interval_without_laps_does_not_judge_the_average():

    plan = _plan(_session("Tuesday", "Intervalado", km=7.2, fast="3:45", slow="3:55", steps=INTERVAL_STEPS))

    text = ExecutionLog.render([plan], [_run(22, 7.3, 370, 150, 1)], {}, [], TODAY)

    line = text.splitlines()[-1]

    assert "tiros (alvo 3:45-3:55) sem voltas medidas" in line
    assert "mais lento" not in line


def test_perception_of_the_session_rides_along():

    plan = _plan(_session("Saturday", "Longão", km=14.0))
    rpe = SimpleNamespace(day="2026-09-26", rpe=7, feel="perna pesada")

    text = ExecutionLog.render([plan], [_run(26, 14.0, 400, 150, 1)], {}, [rpe], TODAY)

    assert "sentiu 7/10 (perna pesada)" in text


def test_steps_rule_forbids_slicing_a_continuous_run_per_km():
    """Mauricio 25-26/09: rodagem e longão fatiados em 8-9 passos de 1 km —
    cada km apitava como um bloco novo."""

    assert "Nunca fatie um contínuo em passos de 1 km" in STEPS_RULE


def test_strides_of_20_seconds_stay_20_seconds_on_the_watch():
    """A IA manda 0.33 min; int() truncava pra 19 s (Mauricio 01/10)."""

    steps = parse_steps([{"kind": "interval", "duration_min": 0.33}])

    assert steps[0].duration_sec == 20


def test_fartlek_average_is_never_judged_against_the_fast_range():
    """Plano antigo com fartlek num passo só (alvo 5:20-6:00): a média 6:13
    não é "13s mais lento" — fartlek alterna forte e trote."""

    steps = [WorkoutStep(kind="run", distance_m=8000, pace_min="5:20", pace_max="6:00")]
    plan = _plan(_session("Tuesday", "Fartlek", km=8.0, steps=steps))

    text = ExecutionLog.render([plan], [_run(22, 8.0, 373, 146, 1)], {}, [], TODAY)

    assert text.endswith("ter 22/09 · Fartlek (8 km; alvo 5:20-6:00) → 8.0 km a 6:13, FC 146")
