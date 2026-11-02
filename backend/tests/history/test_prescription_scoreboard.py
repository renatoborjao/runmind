"""PLACAR DA PRESCRIÇÃO COM ESTE ATLETA (nº 92). O coach via cada sessão ("alvo 6:50-7:32 → fez
6:32, FC 144") mas nunca o resumo do próprio erro: nos leves do Leonardo, 5 de 6 mais rápidos que a
faixa; nas voltas dos fortes, 24 de 31 mais rápidas. É DADO + conhecimento, nunca regra: o coach
decide se o alvo, a dose ou nada muda."""

from datetime import date, datetime, timezone

from app.application.history import prescription_scoreboard
from app.application.history.prescription_scoreboard import MIN_N, Tally, assess, render
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import WorkoutStep
from tests.coach.factories import make_activity

WEEK_1 = date(2026, 10, 5)      # segunda
WEEK_2 = date(2026, 10, 12)
WEEK_3 = date(2026, 10, 19)
TODAY = date(2026, 10, 28)

EASY_STEPS = [WorkoutStep(kind="run", distance_m=6000, pace_min="6:50", pace_max="7:30")]


def _session(day, workout_type, km, steps=None, fast=None, slow=None):

    session = PlannedSession(
        day=day, workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=fast, target_pace_max=slow,
    )

    session.steps = steps or []

    return session


def _plan(week_start, *sessions, volume=20.0):

    return TrainingPlan(
        athlete_name="L", objective="10k", phase="BUILD", weekly_volume=volume,
        running_days=[s.day for s in sessions], week_start=week_start, sessions=list(sessions),
    )


def _run(day: date, km: float, pace_sec: int, hr: int, act_id: int):

    return make_activity(
        id=act_id, start_date=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc),
        distance=km * 1000, moving_time=int(km * pace_sec),
        average_speed=1000 / pace_sec, average_heartrate=hr,
    )


def _leonardo_like():
    """Seis leves, todos mais rápidos que a faixa (6:50-7:30) e todos com a FC dentro do teto."""

    plans, runs = [], []

    for i, week in enumerate((WEEK_1, WEEK_2, WEEK_3)):

        plans.append(
            _plan(
                week,
                _session("Monday", "Rodagem Leve", 6.0, EASY_STEPS),
                _session("Friday", "Rodagem Leve", 6.0, EASY_STEPS),
            )
        )

        runs.append(_run(week, 6.0, 400, 140, 10 + i))                           # seg: 6:40
        runs.append(_run(date(week.year, week.month, week.day + 4), 6.0, 395, 142, 20 + i))

    return plans, runs


def test_a_deviation_always_to_the_same_side_shows_up_with_the_hr_inside_the_ceiling():

    plans, runs = _leonardo_like()

    board = assess(plans, runs, {}, 152, TODAY)

    assert board.prescribed == 6 and board.done == 6

    easy = next(t for t in board.pace if t.label == "rodagem leve / regenerativo")

    assert easy.n == 6 and easy.inside == 0 and len(easy.faster) == 6 and not easy.slower
    assert board.hr_n == 6 and board.hr_within == 6 and board.ceiling == 152

    text = render(board)

    assert "PLACAR DA PRESCRIÇÃO COM ELE" in text
    assert "fez 6 de 6 sessões prescritas (100%)" in text
    assert "de 6 corridas: 0 na faixa; 6 mais rápidas" in text
    assert "FC média dentro do teto aeróbico (152 bpm) em 6 de 6" in text
    # conhecimento, não ordem: separa viés de variação do dia
    assert "CONHECIMENTO, não regra" in text and "variação do dia" in text
    assert "ajustar o alvo, a dose ou nada" in text


def test_a_run_that_changes_side_is_counted_on_both_sides():

    plans, runs = _leonardo_like()

    runs[0] = _run(WEEK_1, 6.0, 470, 140, 10)             # 7:50: mais lento que a faixa

    easy = next(t for t in assess(plans, runs, {}, 152, TODAY).pace)

    assert len(easy.slower) == 1 and len(easy.faster) == 5


def test_below_the_minimum_sample_nothing_is_said():

    plans = [_plan(WEEK_1, _session("Monday", "Rodagem Leve", 6.0, EASY_STEPS))]
    runs = [_run(WEEK_1, 6.0, 400, 140, 1)]

    board = assess(plans, runs, {}, 152, TODAY)

    assert board.pace == [] and render(board) == ""
    assert assess([], [], {}, 152, TODAY) is None
    assert render(None) == ""


def test_distance_is_counted_within_above_and_below_ten_percent():

    plans = [
        _plan(WEEK_1, _session("Monday", "Rodagem Leve", 10.0), _session("Wednesday", "Rodagem Leve", 10.0),
              _session("Friday", "Rodagem Leve", 10.0)),
        _plan(WEEK_2, _session("Monday", "Rodagem Leve", 10.0)),
    ]

    runs = [
        _run(WEEK_1, 10.4, 400, 140, 1),                                   # +4%: dentro
        _run(date(2026, 10, 7), 12.5, 400, 140, 2),                        # +25%: acima
        _run(date(2026, 10, 9), 8.0, 400, 140, 3),                         # -20%: abaixo
        _run(WEEK_2, 10.0, 400, 140, 4),                                   # exato: dentro
    ]

    board = assess(plans, runs, {}, None, TODAY)

    assert (board.dist_n, board.dist_within, board.dist_over, board.dist_under) == (4, 2, 1, 1)
    assert "2 de 4 sessões ficaram a ±10% do prescrito; 1 acima e 1 abaixo" in render(board)


def test_the_average_pace_does_not_judge_a_session_with_intervals():
    """No limiar a média da corrida inclui aquecimento e trote: ali valem as voltas do relógio."""

    steps = [
        WorkoutStep(kind="warmup", distance_m=2000),
        WorkoutStep(kind="repeat", reps=4, steps=[
            WorkoutStep(kind="interval", distance_m=1000, pace_min="6:15", pace_max="6:25"),
            WorkoutStep(kind="recovery", distance_m=200),
        ]),
    ]

    plans = [_plan(w, _session("Friday", "Limiar", 7.0, steps)) for w in (WEEK_1, WEEK_2, WEEK_3)]
    runs = [_run(date(w.year, w.month, w.day + 4), 7.0, 430, 150, 30 + i) for i, w in enumerate((WEEK_1, WEEK_2, WEEK_3))]

    assert assess(plans, runs, {}, 152, TODAY).pace == []


def test_the_watch_laps_of_the_strong_sessions_are_tallied_against_the_target():

    steps = [
        WorkoutStep(kind="repeat", reps=4, steps=[
            WorkoutStep(kind="interval", distance_m=1000, pace_min="6:15", pace_max="6:25"),
        ]),
    ]

    friday = date(2026, 10, 9)

    plans = [_plan(WEEK_1, _session("Friday", "Limiar", 7.0, steps))]
    runs = [_run(friday, 7.0, 430, 150, 77)]

    log = {77: {"date": friday.isoformat(), "km": 7.0, "blocks": [
        {"kind": "interval", "m": 1000, "pace": "6:05", "hr": 150, "target": "6:15-6:25", "ok": False},
        {"kind": "interval", "m": 1000, "pace": "6:04", "hr": 150, "target": "6:15-6:25", "ok": False},
        {"kind": "interval", "m": 1000, "pace": "6:20", "hr": 150, "target": "6:15-6:25", "ok": True},
        {"kind": "interval", "m": 1000, "pace": "6:30", "hr": 150, "target": "6:15-6:25", "ok": False},
    ]}}

    board = assess(plans, runs, log, 152, TODAY)

    tally = board.blocks[0]

    assert tally.label == "limiar" and tally.n == 4 and tally.inside == 1
    assert sorted(tally.faster) == [10, 11] and tally.slower == [5]

    assert "limiar (voltas do relógio contra o alvo): de 4 voltas: 1 no alvo" in render(board)


def test_the_weekly_volume_is_listed_for_closed_weeks_only():

    plans = [
        _plan(WEEK_1, _session("Monday", "Rodagem Leve", 10.0), volume=20.0),
        _plan(WEEK_2, _session("Monday", "Rodagem Leve", 10.0), volume=22.0),
        _plan(WEEK_3, _session("Monday", "Rodagem Leve", 10.0), volume=24.0),
        _plan(date(2026, 10, 26), _session("Wednesday", "Rodagem Leve", 10.0), volume=26.0),   # em andamento
    ]

    runs = [_run(WEEK_1, 10.0, 400, 140, 1), _run(WEEK_2, 10.0, 400, 140, 2), _run(WEEK_3, 12.0, 400, 140, 3)]

    board = assess(plans, runs, {}, None, TODAY)

    assert [(w.day, p, d) for w, p, d in board.volume] == [(5, 20.0, 10.0), (12, 22.0, 10.0), (19, 24.0, 12.0)]
    assert "Volume semanal (prescrito → feito, km): 05/10 20→10, 12/10 22→10, 19/10 24→12" in render(board)


def test_strides_are_left_out_of_the_lap_stats_because_the_gps_cannot_measure_them():

    assert prescription_scoreboard.STRIDES in prescription_scoreboard._NO_BLOCK_STATS
    assert MIN_N >= 3 and isinstance(Tally("x"), Tally)
